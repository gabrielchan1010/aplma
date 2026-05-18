import hashlib
import logging
import re
import shutil
from pathlib import Path

from docling_core.types.doc import DoclingDocument, SectionHeaderItem

import aplma.config as config
from aplma.ingestion.parser import parse_pdf

logger = logging.getLogger(__name__)

_CLAUSE_ONE_RE = re.compile(r"^1\.\s+\S")


def _content_id(pdf_path: Path) -> str:
    return hashlib.sha256(pdf_path.read_bytes()).hexdigest()[:16]


def _compute_page_offset(document: DoclingDocument) -> int:
    for item in document.texts:
        if not isinstance(item, SectionHeaderItem):
            continue
        if not item.prov:
            continue
        if _CLAUSE_ONE_RE.match(item.text.strip()):
            return item.prov[0].page_no - 1
    logger.warning(
        "Could not detect Clause 1 heading — page offset defaults to 0. "
        "get_document_toc() page numbers may be incorrect."
    )
    return 0


class DocumentStore:
    def __init__(self, documents_dir: Path | None = None) -> None:
        self._documents_dir = documents_dir or config.DOCUMENTS_DIR
        self._store: dict[str, DoclingDocument] = {}
        self._paths: dict[str, str] = {}
        self._offsets: dict[str, int] = {}
        self._tocs: dict[str, list[dict]] = {}

    def ingest(self, pdf_path: str | Path) -> str:
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        document_id = _content_id(pdf_path)
        if document_id in self._store:
            return document_id
        self._documents_dir.mkdir(exist_ok=True)
        dest = self._documents_dir / f"{document_id}.pdf"
        if not dest.exists():
            shutil.copy(pdf_path, dest)
        doc = parse_pdf(dest)
        self._store[document_id] = doc
        self._paths[document_id] = str(dest)
        self._offsets[document_id] = _compute_page_offset(doc)
        return document_id

    def get(self, document_id: str) -> DoclingDocument:
        if document_id not in self._store:
            raise KeyError(f"No document with id '{document_id}'. Call ingest() first.")
        return self._store[document_id]

    def offset(self, document_id: str) -> int:
        if document_id not in self._offsets:
            raise KeyError(f"No document with id '{document_id}'. Call ingest() first.")
        return self._offsets[document_id]

    def path(self, document_id: str) -> Path:
        if document_id not in self._paths:
            raise KeyError(f"No document with id '{document_id}'. Call ingest() first.")
        return Path(self._paths[document_id])

    def get_toc(self, document_id: str) -> list[dict] | None:
        return self._tocs.get(document_id)

    def set_toc(self, document_id: str, toc: list[dict]) -> None:
        self._tocs[document_id] = toc

    def list_documents(self) -> list[dict]:
        return [
            {"document_id": doc_id, "source_path": path}
            for doc_id, path in self._paths.items()
        ]


_default_store: DocumentStore = DocumentStore()


def ingest_document(pdf_path: str | Path) -> str:
    return _default_store.ingest(pdf_path)


def get_document(document_id: str) -> DoclingDocument:
    return _default_store.get(document_id)


def get_page_offset(document_id: str) -> int:
    return _default_store.offset(document_id)


def get_document_path(document_id: str) -> Path:
    return _default_store.path(document_id)


def get_cached_toc(document_id: str) -> list[dict] | None:
    return _default_store.get_toc(document_id)


def cache_toc(document_id: str, toc: list[dict]) -> None:
    _default_store.set_toc(document_id, toc)
