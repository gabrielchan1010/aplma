"""Step 4 — Slicer: fetch the Scout-selected page ranges as one payload."""
from __future__ import annotations

from aplma.tools.nav_tools import get_document_pages_with_map


def fetch_page_ranges(
    document_id: str, ranges: list[dict]
) -> tuple[str, list[tuple[int, int]]]:
    parts: list[str] = []
    full_map: list[tuple[int, int]] = []
    cursor = 0
    for r in ranges:
        content, local_map = get_document_pages_with_map(
            document_id, int(r["start_page"]), int(r["end_page"])
        )
        if not content:
            continue
        if parts:
            sep = "\n\n--- next range ---\n\n"
            cursor += len(sep)
            parts.append(sep)
        for char_start, page_no in local_map:
            full_map.append((cursor + char_start, page_no))
        parts.append(content)
        cursor += len(content)
    return "".join(parts), full_map
