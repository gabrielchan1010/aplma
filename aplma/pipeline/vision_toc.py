"""Step 2 — Vision TOC extraction."""
from __future__ import annotations

import io
import json
import re
from pathlib import Path

from docling_core.types.doc import DoclingDocument, SectionHeaderItem

from aplma.store.document_store import (
    cache_toc,
    get_cached_toc,
    get_document,
    get_document_path,
    get_page_offset,
)


def get_document_toc(document_id: str) -> list[dict]:
    cached = get_cached_toc(document_id)
    if cached is not None:
        return cached

    document = get_document(document_id)
    toc_pages = _detect_toc_pages(document)
    offset = get_page_offset(document_id)
    pdf_path = get_document_path(document_id)
    toc = _toc_via_vision(pdf_path, toc_pages, offset)
    cache_toc(document_id, toc)
    return toc


def _detect_toc_pages(document: DoclingDocument) -> list[int]:
    for item in document.texts:
        if not isinstance(item, SectionHeaderItem):
            continue
        if not item.prov:
            continue
        if item.text.strip().upper() in ("CONTENTS", "TABLE OF CONTENTS", "CONTENTS PAGE"):
            p = item.prov[0].page_no
            return [p, p + 1]

    import aplma.config as config
    return list(config.TOC_PAGES)


def _toc_via_vision(pdf_path: Path, toc_pages: list[int], offset: int) -> list[dict]:
    try:
        import pypdfium2 as pdfium
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise ImportError(
            "TOC vision extraction requires the runtime dependencies. "
            "Run: pip install aplma"
        ) from exc

    import aplma.config as config

    if not config.GEMINI_API_KEY:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. Add it to .env or set it as an environment variable."
        )

    def _page_to_bytes(page_no: int) -> bytes:
        pdf = pdfium.PdfDocument(str(pdf_path))
        bitmap = pdf[page_no - 1].render(scale=100 / 72)
        buf = io.BytesIO()
        bitmap.to_pil().save(buf, format="PNG")
        return buf.getvalue()

    images = [
        types.Part.from_bytes(data=_page_to_bytes(p), mime_type="image/png")
        for p in toc_pages
    ]

    prompt = (
        "These images show the table of contents of a legal facility agreement.\n\n"
        "Extract every row as a JSON array:\n"
        '[{"number": "1.", "title": "Definitions and Interpretation", "document_page": 1}, ...]\n\n'
        "Rules:\n"
        "- number: the clause or schedule number from the left column\n"
        "- title: the clause title, clean — no dot leaders, no trailing numbers\n"
        "- document_page: the integer page number from the right column\n"
        "- Include every row that has a page number\n"
        "- Return only the JSON array, no explanation"
    )

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    response = client.models.generate_content(
        model=config.VISION_TOC_MODEL,
        contents=[*images, prompt],
    )

    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    if not raw.startswith("["):
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            raw = match.group(0)

    entries = json.loads(raw)
    return [
        {
            "number": e["number"],
            "title":  e["title"],
            "page":   e["document_page"] + offset,
        }
        for e in entries
        if e.get("document_page")
    ]
