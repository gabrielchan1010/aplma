"""Step 5 — deterministic structural parser for Docling output."""
from __future__ import annotations

import logging
from typing import Any, Callable, Iterator

from pydantic import BaseModel
from docling_core.types.doc import SectionHeaderItem

from aplma.models.covenant import (
    FinancialIndebtednessCovenant,
    FinancialIndebtednessDefinition,
    FinancialIndebtednessRestriction,
    GroundedSpan,
    PermittedFinancialIndebtednessCarveOut,
)
from aplma.specs.loader import ExtractionSpec
from aplma.store.document_store import get_document


_DEFAULT_ANCHORS: dict[str, dict[str, list[str]]] = {
    "financial_indebtedness": {
        "fi_definition": ["Financial Indebtedness means"],
        "permitted_fi_definition": ["Permitted Financial Indebtedness means"],
        "restriction_heading_suffix": ["Financial Indebtedness"],
    },
}


def _resolve_anchors(
    covenant_type: str,
    spec: ExtractionSpec | None,
    key: str,
) -> list[str]:
    if spec is not None:
        patterns = spec.structural_anchors.get(key)
        if patterns:
            return patterns
    return _DEFAULT_ANCHORS.get(covenant_type, {}).get(key, [])

logger = logging.getLogger(__name__)

_PARSERS: dict[str, Callable[..., BaseModel]] = {}


def parser_for(covenant_type: str) -> Callable[..., BaseModel] | None:
    return _PARSERS.get(covenant_type)


def has_parser(covenant_type: str) -> bool:
    return covenant_type in _PARSERS


def run_structural_parse(
    covenant_type: str,
    document_id: str,
    scout_ranges: list[dict],
    slice_content: str,
    spec: ExtractionSpec | None = None,
) -> BaseModel:
    fn = _PARSERS.get(covenant_type)
    if fn is None:
        raise ValueError(
            f"No structural parser registered for covenant_type={covenant_type!r}. "
            f"Known parsers: {sorted(_PARSERS)}"
        )
    return fn(
        document_id=document_id,
        scout_ranges=scout_ranges,
        slice_content=slice_content,
        spec=spec,
    )


def parse_financial_indebtedness(
    document_id: str,
    scout_ranges: list[dict],
    slice_content: str,
    spec: ExtractionSpec | None = None,
) -> FinancialIndebtednessCovenant:
    document = get_document(document_id)
    pages_in_scope = _pages_from_ranges(scout_ranges)
    items: list[Any] = [
        item for item in document.texts
        if item.prov and item.prov[0].page_no in pages_in_scope
    ]
    logger.info(
        "Structural parser: %d items across %d in-scope pages",
        len(items), len(pages_in_scope),
    )

    fi_patterns = _resolve_anchors("financial_indebtedness", spec, "fi_definition")
    permitted_patterns = _resolve_anchors("financial_indebtedness", spec, "permitted_fi_definition")
    restriction_suffixes = _resolve_anchors("financial_indebtedness", spec, "restriction_heading_suffix")

    return FinancialIndebtednessCovenant(
        fi_definition=_extract_fi_definition(items, slice_content, fi_patterns),
        restriction=_extract_restriction(items, slice_content, restriction_suffixes),
        permitted_carve_outs=_extract_permitted_carve_outs(items, slice_content, permitted_patterns),
    )


def _extract_fi_definition(
    items: list[Any],
    slice_content: str,
    anchor_patterns: list[str],
) -> FinancialIndebtednessDefinition | None:
    anchor_idx = _find_first_matching_anchor(items, anchor_patterns)
    if anchor_idx < 0:
        logger.warning("FI definition anchor not found (tried patterns: %r)", anchor_patterns)
        return None

    anchor = items[anchor_idx]
    sub_items = list(_walk_sub_items(items, anchor_idx))
    if not sub_items:
        sub_items = list(_walk_body_items(items, anchor_idx))
        if sub_items:
            logger.info("FI definition is prose (no (a)/(b) sub-items) — using body walker.")

    parts = [anchor.text.strip()] + [si.text.strip() for si in sub_items]
    definition_text = "\n".join(parts)

    return FinancialIndebtednessDefinition(
        clause_ref="Clause 1.1",
        definition_text=definition_text,
        grounding=_make_grounding(
            text=definition_text,
            page=anchor.prov[0].page_no,
            slice_content=slice_content,
        ),
    )


def _extract_restriction(
    items: list[Any],
    slice_content: str,
    heading_suffixes: list[str],
) -> FinancialIndebtednessRestriction | None:
    for i, item in enumerate(items):
        if not isinstance(item, SectionHeaderItem):
            continue
        heading_text = item.text.strip()
        matched_suffix = next(
            (s for s in heading_suffixes if heading_text.endswith(s)), None
        )
        if matched_suffix is None:
            continue
        prefix = heading_text[: -len(matched_suffix)].strip()
        if not prefix or not all(ch.isdigit() or ch == "." for ch in prefix):
            continue

        sub_items = list(_walk_sub_items(items, i))
        if not sub_items:
            sub_items = list(_walk_body_items(items, i))
            if not sub_items:
                logger.warning("Restriction heading %r has no body items at all", heading_text)
                continue
            logger.info("Restriction %r is prose (no (a)/(b) sub-items) — using body walker.", heading_text)

        restriction_text = "\n".join(si.text.strip() for si in sub_items)
        return FinancialIndebtednessRestriction(
            clause_ref=f"Clause {prefix}",
            restriction_text=restriction_text,
            grounding=_make_grounding(
                text=restriction_text,
                page=item.prov[0].page_no,
                slice_content=slice_content,
            ),
        )

    logger.warning("Restriction heading not found (tried suffixes: %r)", heading_suffixes)
    return None


def _extract_permitted_carve_outs(
    items: list[Any],
    slice_content: str,
    anchor_patterns: list[str],
) -> list[PermittedFinancialIndebtednessCarveOut]:
    anchor_idx = _find_first_matching_anchor(items, anchor_patterns)
    if anchor_idx < 0:
        logger.warning(
            "Permitted Financial Indebtedness anchor not found (tried patterns: %r)", anchor_patterns
        )
        return []

    carve_outs: list[PermittedFinancialIndebtednessCarveOut] = []
    for item in _walk_sub_items(items, anchor_idx):
        text = item.text.strip()
        page = item.prov[0].page_no
        carve_outs.append(
            PermittedFinancialIndebtednessCarveOut(
                carve_out_text=text,
                grounding=_make_grounding(text=text, page=page, slice_content=slice_content),
            )
        )
    return carve_outs


_QUOTE_CHARS = '"\'"“”‘’«»'


def _normalize_for_anchor(text: str) -> str:
    if not text:
        return ""
    stripped = "".join(ch for ch in text if ch not in _QUOTE_CHARS)
    return " ".join(stripped.split()).lower()


def _find_anchor_by_prefix(items: list[Any], prefix: str) -> int:
    norm_prefix = _normalize_for_anchor(prefix)
    if not norm_prefix:
        return -1
    for i, item in enumerate(items):
        if _normalize_for_anchor(item.text).startswith(norm_prefix):
            return i
    return -1


def _find_first_matching_anchor(items: list[Any], patterns: list[str]) -> int:
    for pattern in patterns:
        idx = _find_anchor_by_prefix(items, pattern)
        if idx >= 0:
            return idx
    return -1


def _walk_sub_items(items: list[Any], anchor_idx: int) -> Iterator[Any]:
    for i in range(anchor_idx + 1, len(items)):
        item = items[i]
        if isinstance(item, SectionHeaderItem):
            return
        if not item.text.lstrip().startswith("("):
            return
        yield item


def _walk_body_items(items: list[Any], anchor_idx: int) -> Iterator[Any]:
    for i in range(anchor_idx + 1, len(items)):
        item = items[i]
        if isinstance(item, SectionHeaderItem):
            return
        yield item


def _parse_label(text: str) -> str | None:
    s = text.lstrip()
    if not s.startswith("("):
        return None
    close = s.find(")")
    if close <= 1:
        return None
    label = s[1:close]
    if not label or not all(ch.isalnum() for ch in label):
        return None
    return label


def _make_grounding(*, text: str, page: int, slice_content: str) -> GroundedSpan:
    if not slice_content:
        return GroundedSpan(page_number=page, extraction_text=text, verbatim=True)

    if "\n" in text:
        lines = [ln for ln in text.split("\n") if ln.strip()]
        if not lines:
            return GroundedSpan(page_number=page, extraction_text=text, verbatim=True)
        start = slice_content.find(lines[0])
        last_pos = slice_content.find(lines[-1])
        if start < 0 or last_pos < 0:
            return GroundedSpan(page_number=page, extraction_text=text, verbatim=True)
        end = last_pos + len(lines[-1])
        return GroundedSpan(
            page_number=page,
            extraction_text=text,
            verbatim=True,
            char_start=start,
            char_end=end,
        )

    start = slice_content.find(text)
    if start < 0:
        return GroundedSpan(page_number=page, extraction_text=text, verbatim=True)
    return GroundedSpan(
        page_number=page,
        extraction_text=text,
        verbatim=True,
        char_start=start,
        char_end=start + len(text),
    )


def _pages_from_ranges(scout_ranges: list[dict]) -> set[int]:
    pages: set[int] = set()
    for r in scout_ranges:
        for p in range(int(r["start_page"]), int(r["end_page"]) + 1):
            pages.add(p)
    return pages


_PARSERS["financial_indebtedness"] = parse_financial_indebtedness
