from pathlib import Path

from docling.datamodel.document import ConversionResult
from docling.document_converter import DocumentConverter
from docling_core.types.doc import DoclingDocument


def parse_pdf(pdf_path: str | Path) -> DoclingDocument:
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    try:
        converter = DocumentConverter()
        result: ConversionResult = converter.convert(str(pdf_path))
        return result.document
    except Exception as exc:
        raise RuntimeError(f"Docling conversion failed for {pdf_path.name}: {exc}") from exc
