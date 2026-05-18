"""Per-covenant orchestrator — chains the five pipeline steps together."""
from __future__ import annotations

from pydantic import BaseModel

from aplma.pipeline.scout import identify_pages
from aplma.pipeline.slicer import fetch_page_ranges
from aplma.pipeline.structural_parser import run_structural_parse
from aplma.pipeline.vision_toc import get_document_toc
from aplma.specs.loader import ExtractionSpec


def extract_covenant(document_id: str, spec: ExtractionSpec) -> BaseModel:
    """Run Steps 2–5 of the pipeline for a single covenant spec."""
    toc = get_document_toc(document_id)
    scout_result = identify_pages(toc, spec, document_id)
    content, _page_map = fetch_page_ranges(document_id, scout_result["ranges"])
    return run_structural_parse(
        covenant_type=spec.covenant_type,
        document_id=document_id,
        scout_ranges=scout_result["ranges"],
        slice_content=content,
        spec=spec,
    )
