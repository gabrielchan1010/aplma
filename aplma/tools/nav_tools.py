"""Navigation primitives used by the Scout and the Slicer."""
from docling_core.types.doc import DoclingDocument, SectionHeaderItem

from aplma.store.document_store import get_document


def get_table_of_contents(document_id: str) -> list[dict]:
    document = get_document(document_id)
    toc = []
    for item in document.texts:
        if not isinstance(item, SectionHeaderItem):
            continue
        if not item.prov:
            continue
        toc.append({
            "level": item.level,
            "text": item.text.strip(),
            "page_number": item.prov[0].page_no,
        })
    return toc


def search_headings(document_id: str, query: str) -> list[dict]:
    q = query.lower()
    return [
        {"text": e["text"], "page": e["page_number"]}
        for e in get_table_of_contents(document_id)
        if q in e["text"].lower()
    ]


def search_document_text(document_id: str, query: str) -> list[dict]:
    q = query.lower()
    document = get_document(document_id)
    seen: set[int] = set()
    results: list[dict] = []
    for item in document.texts:
        if not item.prov or q not in item.text.lower():
            continue
        page = item.prov[0].page_no
        if page not in seen:
            seen.add(page)
            results.append({"page": page, "snippet": item.text[:150]})
    return sorted(results, key=lambda r: r["page"])


def get_document_pages(document_id: str, start_page: int, end_page: int) -> str:
    content, _ = get_document_pages_with_map(document_id, start_page, end_page)
    return content


def get_document_pages_with_map(
    document_id: str, start_page: int, end_page: int
) -> tuple[str, list[tuple[int, int]]]:
    if start_page < 1:
        raise ValueError(f"start_page must be >= 1, got {start_page}")
    if end_page < start_page:
        raise ValueError(f"end_page ({end_page}) must be >= start_page ({start_page})")

    document = get_document(document_id)
    chunks: list[tuple[int, str]] = []

    for item in document.texts:
        if not item.prov:
            continue
        page_no = item.prov[0].page_no
        if start_page <= page_no <= end_page:
            chunks.append((page_no, item.text))

    for item in document.tables:
        if not item.prov:
            continue
        page_no = item.prov[0].page_no
        if start_page <= page_no <= end_page:
            chunks.append((page_no, item.export_to_markdown(doc=document)))

    chunks.sort(key=lambda x: x[0])

    parts: list[str] = []
    page_map: list[tuple[int, int]] = []
    cursor = 0
    sep = "\n\n"
    for i, (page_no, text) in enumerate(chunks):
        if i > 0:
            cursor += len(sep)
            parts.append(sep)
        page_map.append((cursor, page_no))
        parts.append(text)
        cursor += len(text)

    return "".join(parts), page_map
