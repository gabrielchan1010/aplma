"""Captures one full pipeline run per covenant spec for the static review report."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from aplma.pipeline.scout import _scout_system_prompt, identify_pages
from aplma.pipeline.slicer import fetch_page_ranges
from aplma.pipeline.structural_parser import has_parser, run_structural_parse
from aplma.pipeline.vision_toc import get_document_toc
from aplma.specs.loader import ExtractionSpec, load_spec
from aplma.store.document_store import get_page_offset, ingest_document
from aplma.tools.nav_tools import get_table_of_contents


@dataclass
class DocumentState:
    document_id: str
    document_name: str
    page_offset: int
    headings: list[dict]

    def html(self):
        from aplma.report import inline_display
        return inline_display.document_state_html(self)


@dataclass
class TocResult:
    document_name: str
    entries: list[dict]

    def html(self):
        from aplma.report import inline_display
        return inline_display.toc_html(self)


@dataclass
class ScoutResult:
    spec_name: str
    covenant_type: str
    system_prompt: str
    user_prompt: str
    trace: list[dict]
    result: dict | None
    error: Exception | None

    @property
    def ranges(self) -> list[dict]:
        return list((self.result or {}).get("ranges", []))

    @property
    def rationale(self) -> str:
        return (self.result or {}).get("rationale", "")

    def html(self):
        from aplma.report import inline_display
        return inline_display.scout_html(self)


@dataclass
class SliceResult:
    spec_name: str
    covenant_type: str
    ranges: list[dict]
    slice_content: str
    page_map: list[tuple[int, int]]
    error: Exception | None = None

    def html(self):
        from aplma.report import inline_display
        return inline_display.slice_html(self)


@dataclass
class ReviewSession:
    spec_name: str
    spec: ExtractionSpec
    document_id: str
    document_name: str
    page_offset: int
    docling_headings: list[dict]
    doc_toc: list[dict]

    scout_system_prompt: str = ""
    scout_user_prompt: str = ""
    scout_trace: list[dict] = field(default_factory=list)
    scout_result: dict | None = None
    scout_error: Exception | None = None

    slice_content: str = ""
    page_map: list[tuple[int, int]] = field(default_factory=list)
    ranges: list[dict] = field(default_factory=list)

    structural_extraction_summary: str = ""
    rule: BaseModel | None = None
    extract_error: Exception | None = None

    @property
    def failed_stage(self) -> str | None:
        if self.scout_error is not None:
            return "scout"
        if self.extract_error is not None:
            return "structural_extraction"
        if self.rule is None:
            return "structural_extraction"
        return None

    def html(self):
        from aplma.report import inline_display
        return inline_display.structural_extraction_html(self)


def ingest_pdf(pdf_path: Path | str) -> DocumentState:
    pdf_path = Path(pdf_path)
    document_id = ingest_document(pdf_path)
    return DocumentState(
        document_id=document_id,
        document_name=pdf_path.name,
        page_offset=get_page_offset(document_id),
        headings=get_table_of_contents(document_id),
    )


def run_vision_toc(doc: DocumentState) -> TocResult:
    try:
        entries = get_document_toc(doc.document_id)
    except Exception as exc:
        if not _is_retryable(exc):
            raise
        print(
            f"  ⚠ Vision TOC hit a transient error ({type(exc).__name__}). "
            "Waiting 10s and retrying once...",
            flush=True,
        )
        time.sleep(10)
        try:
            entries = get_document_toc(doc.document_id)
        except Exception as retry_exc:
            raise RuntimeError(
                "Vision TOC failed twice — Gemini is unavailable right now. "
                "Wait a minute or two, then re-run only this cell."
            ) from retry_exc
    return TocResult(document_name=doc.document_name, entries=entries)


def run_scout(
    doc: DocumentState,
    toc: TocResult,
    spec: ExtractionSpec,
    spec_name: str | None = None,
    max_retries: int = 3,
) -> ScoutResult:
    name = spec_name or getattr(spec, "covenant_type", "covenant")

    def _print_tool_call(entry: dict, n: int) -> None:
        tool = entry["tool"]
        hits = entry.get("result") or []
        print(f'    [{n}] {tool}({entry["args"].get("query", "")!r}) → {len(hits)} result(s)', flush=True)

    trace: list[dict] = []
    result: dict | None = None
    error: Exception | None = None

    for attempt in range(max_retries):
        if attempt > 0:
            print('    Retrying — sending request to Gemini...', flush=True)
        trace = []
        try:
            result = identify_pages(toc.entries, spec, doc.document_id, trace=trace)
            error = None
        except Exception as exc:
            result = None
            error = exc
        for i, entry in enumerate(trace, start=1):
            _print_tool_call(entry, i)
        if error is None or not _is_retryable(error):
            break
        if attempt < max_retries - 1:
            delay = 5 * (2 ** attempt)
            print(
                f'  Scout for {name}: transient error ({type(error).__name__}), '
                f'retrying in {delay}s (attempt {attempt + 1}/{max_retries})...',
                flush=True,
            )
            time.sleep(delay)

    return ScoutResult(
        spec_name=name,
        covenant_type=spec.covenant_type,
        system_prompt=_scout_system_prompt(),
        user_prompt=_scout_user_prompt(toc.entries, spec),
        trace=trace,
        result=result,
        error=error,
    )


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc)
    if any(code in msg for code in ("500", "503", "429", "INTERNAL", "UNAVAILABLE")):
        return True
    transient_class_names = {
        "RemoteProtocolError", "ConnectError", "ConnectTimeout",
        "ReadTimeout", "WriteTimeout", "PoolTimeout", "NetworkError",
    }
    return type(exc).__name__ in transient_class_names


def _scout_user_prompt(doc_toc: list[dict], spec: ExtractionSpec) -> str:
    return (
        "Table of contents (physical PDF page numbers, ready to use):\n"
        f"{json.dumps(doc_toc, indent=2)}\n\n"
        f"{spec.navigation_hint.strip()}\n\n"
        "Return one tight range per logical section (definition / restriction). "
        "Do not merge them. Use the JSON schema in the system instructions."
    )


def run_slicer(doc: DocumentState, scout: ScoutResult) -> SliceResult:
    ranges = scout.ranges
    if not ranges:
        return SliceResult(
            spec_name=scout.spec_name,
            covenant_type=scout.covenant_type,
            ranges=[],
            slice_content="",
            page_map=[],
            error=scout.error,
        )
    try:
        slice_content, page_map = fetch_page_ranges(doc.document_id, ranges)
    except Exception as exc:
        return SliceResult(
            spec_name=scout.spec_name,
            covenant_type=scout.covenant_type,
            ranges=ranges,
            slice_content="",
            page_map=[],
            error=exc,
        )
    return SliceResult(
        spec_name=scout.spec_name,
        covenant_type=scout.covenant_type,
        ranges=ranges,
        slice_content=slice_content,
        page_map=page_map,
    )


def run_structural_extraction(
    doc: DocumentState,
    toc: TocResult,
    scout: ScoutResult,
    slice_: SliceResult,
    spec: ExtractionSpec,
    spec_name: str | None = None,
) -> ReviewSession:
    session = ReviewSession(
        spec_name=spec_name or scout.spec_name,
        spec=spec,
        document_id=doc.document_id,
        document_name=doc.document_name,
        page_offset=doc.page_offset,
        docling_headings=doc.headings,
        doc_toc=toc.entries,
        scout_system_prompt=scout.system_prompt,
        scout_user_prompt=scout.user_prompt,
        scout_trace=scout.trace,
        scout_result=scout.result,
        scout_error=scout.error,
        slice_content=slice_.slice_content,
        page_map=slice_.page_map,
        ranges=slice_.ranges,
        structural_extraction_summary=(
            f"Structural parser ({spec.covenant_type}) — deterministic walk of "
            f"Docling text items. See aplma/pipeline/structural_parser.py."
        ),
    )

    if slice_.error is not None:
        session.extract_error = slice_.error
        return session
    if not slice_.slice_content:
        return session

    if not has_parser(spec.covenant_type):
        session.extract_error = ValueError(
            f"No structural parser registered for covenant_type={spec.covenant_type!r}. "
            "Add one in aplma/pipeline/structural_parser.py."
        )
        return session

    try:
        session.rule = run_structural_parse(
            covenant_type=spec.covenant_type,
            document_id=doc.document_id,
            scout_ranges=slice_.ranges,
            slice_content=slice_.slice_content,
            spec=spec,
        )
    except Exception as exc:
        session.extract_error = exc
    return session


def build_sessions(
    pdf_path: Path,
    spec_paths: list[Path],
) -> list[ReviewSession]:
    doc = ingest_pdf(pdf_path)
    toc = run_vision_toc(doc)

    sessions: list[ReviewSession] = []
    for spec_path in spec_paths:
        spec_name = Path(spec_path).stem
        spec = load_spec(spec_path)
        scout = run_scout(doc, toc, spec, spec_name=spec_name)
        slice_ = run_slicer(doc, scout)
        session = run_structural_extraction(
            doc, toc, scout, slice_, spec, spec_name=spec_name
        )
        sessions.append(session)
    return sessions


__all__ = [
    "DocumentState", "TocResult", "ScoutResult", "SliceResult", "ReviewSession",
    "ingest_pdf", "run_vision_toc", "run_scout", "run_slicer",
    "run_structural_extraction", "build_sessions",
]
