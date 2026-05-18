"""Step 3 — LLM Scout for identifying which pages hold the target covenant."""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator

from aplma import config
from aplma.specs.loader import ExtractionSpec
from aplma.tools.nav_tools import (
    search_document_text,
    search_headings,
)

logger = logging.getLogger(__name__)


class PageRange(BaseModel):
    start_page: int = Field(ge=1)
    end_page: int = Field(ge=1)
    label: str = Field(default="", description="Short tag — e.g. 'definition', 'restriction'")

    @model_validator(mode="after")
    def _end_after_start(self) -> "PageRange":
        if self.end_page < self.start_page:
            raise ValueError(
                f"end_page ({self.end_page}) must be >= start_page ({self.start_page})"
            )
        return self


class PageRanges(BaseModel):
    ranges: list[PageRange] = Field(min_length=1)
    rationale: str


def _scout_system_prompt() -> str:
    if config.SCOUT_MAX_TOOL_CALLS == 0:
        tools_block = (
            "Pre-fetched search results will be provided in the user prompt. "
            "Use ONLY those results — you have no tools and cannot search further. "
            "Identify the page ranges directly from the TOC and the pre-fetch hits.\n\n"
        )
    else:
        tools_block = (
            "You have two tools available:\n"
            "  1. search_headings(query) — searches the document's Docling-detected section "
            "headings by keyword. Returns heading text and physical PDF page numbers. "
            "Use this first — it is fast and precise.\n"
            "  2. search_document_text(query) — searches ALL page text (paragraphs, tables, "
            "definitions) for a keyword. Returns pages with a short snippet. Use this when "
            "search_headings finds nothing or you need to confirm wording.\n\n"
            f"Call at most {config.SCOUT_MAX_TOOL_CALLS} tools total.\n\n"
        )
    return (
        "You are a legal document analyst working with a facility agreement. "
        "You will be given a table of contents with exact physical PDF page numbers.\n\n"
        + tools_block +
        "A covenant typically lives in TWO different sections of the agreement:\n"
        "  • The restriction clause — in the General Covenants section (late in the document).\n"
        "  • The definition of permitted exceptions — in the Definitions section (Clause 1.1).\n\n"
        "Return ONE TIGHT RANGE PER SECTION — do NOT merge them into a single wide range.\n"
        "Keep each range to 1–2 pages around the relevant heading or text.\n\n"
        "Return JSON ONLY in exactly this shape (no markdown):\n"
        '{"ranges": [\n'
        '    {"start_page": <int>, "end_page": <int>, "label": "<restriction|definition>"},\n'
        '    {"start_page": <int>, "end_page": <int>, "label": "<restriction|definition>"}\n'
        '  ],\n'
        '  "rationale": "<one sentence>"}'
    )


def identify_pages(
    toc: list[dict],
    spec: ExtractionSpec,
    document_id: str,
    *,
    trace: list[dict] | None = None,
) -> dict:
    from google import genai
    from google.genai import types

    if not config.GEMINI_API_KEY:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. Add it to .env or set it as an environment variable."
        )

    prefetch_lines: list[str] = []
    for term in spec.heading_search_terms:
        heading_hits = search_headings(document_id, term)
        text_hits = search_document_text(document_id, term)
        if trace is not None:
            trace.append({"tool": "search_headings", "args": {"query": term}, "result": heading_hits})
            trace.append({"tool": "search_document_text", "args": {"query": term}, "result": text_hits})
        prefetch_lines.append(f'search_headings("{term}"): {json.dumps(heading_hits)}')
        prefetch_lines.append(f'search_document_text("{term}"): {json.dumps(text_hits)}')

    if prefetch_lines:
        tail = (
            f"\n\nYou may call up to {config.SCOUT_MAX_TOOL_CALLS} additional tool(s) "
            "if you need to clarify something not covered above.\n\n"
            if config.SCOUT_MAX_TOOL_CALLS > 0
            else "\n\nNo additional tools are available — use these results.\n\n"
        )
        prefetch_block = (
            "Pre-fetched search results — use these to identify the page ranges:\n"
            + "\n".join(prefetch_lines)
            + tail
        )
    else:
        prefetch_block = ""

    user_prompt = (
        "Table of contents (physical PDF page numbers, ready to use):\n"
        f"{json.dumps(toc, indent=2)}\n\n"
        f"{spec.navigation_hint.strip()}\n\n"
        f"{prefetch_block}"
        "Return one tight range per logical section (definition / restriction). "
        "Do not merge them. Use the JSON schema in the system instructions."
    )

    search_headings_decl = types.FunctionDeclaration(
        name="search_headings",
        description="Search Docling-detected section headings by keyword.",
        parameters={
            "type": "OBJECT",
            "properties": {"query": {"type": "STRING"}},
            "required": ["query"],
        },
    )
    search_text_decl = types.FunctionDeclaration(
        name="search_document_text",
        description="Search all page text for a keyword.",
        parameters={
            "type": "OBJECT",
            "properties": {"query": {"type": "STRING"}},
            "required": ["query"],
        },
    )
    tools_arg: list[Any] = []
    if config.SCOUT_MAX_TOOL_CALLS > 0:
        tool_config = types.Tool(
            function_declarations=[search_headings_decl, search_text_decl]
        )
        tools_arg = [tool_config]

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    contents: list[Any] = [
        types.Content(role="user", parts=[types.Part(text=user_prompt)])
    ]

    final_text: str | None = None
    tool_call_count = 0
    for _ in range(config.SCOUT_MAX_TOOL_CALLS + 1):
        response = client.models.generate_content(
            model=config.ROUTING_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=_scout_system_prompt(),
                tools=tools_arg,
            ),
        )
        candidate = response.candidates[0] if response.candidates else None
        if candidate is None or candidate.content is None:
            break

        parts = candidate.content.parts or []
        function_calls = [p.function_call for p in parts if getattr(p, "function_call", None)]

        if not function_calls:
            final_text = response.text
            break

        if tool_call_count + len(function_calls) > config.SCOUT_MAX_TOOL_CALLS:
            raise RuntimeError(
                f"Scout requested more tool calls than allowed "
                f"({tool_call_count + len(function_calls)} > {config.SCOUT_MAX_TOOL_CALLS})."
            )

        contents.append(candidate.content)
        tool_response_parts: list[Any] = []
        for call in function_calls:
            result = _dispatch_scout_tool(call, document_id, trace=trace)
            tool_call_count += 1
            tool_response_parts.append(
                types.Part.from_function_response(
                    name=call.name,
                    response={"result": result},
                )
            )
        contents.append(types.Content(role="user", parts=tool_response_parts))

    if final_text is None:
        raise RuntimeError(
            f"Scout did not return a final JSON answer after {config.SCOUT_MAX_TOOL_CALLS} tool calls."
        )

    return _parse_page_ranges(final_text).model_dump()


def _dispatch_scout_tool(
    call: Any, document_id: str, *, trace: list[dict] | None = None
) -> Any:
    args = dict(call.args or {})
    name = call.name
    if name == "search_headings":
        result = search_headings(document_id, args.get("query", ""))
        if trace is not None:
            trace.append({"tool": name, "args": args, "result": result})
        return result
    if name == "search_document_text":
        result = search_document_text(document_id, args.get("query", ""))
        if trace is not None:
            trace.append({"tool": name, "args": args, "result": result})
        return result
    raise ValueError(f"Unknown Scout tool: {name}")


def _parse_page_ranges(text: str) -> PageRanges:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    if not raw.startswith("{"):
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1:
            raise ValueError(f"Scout response is not JSON: {text!r}")
        raw = raw[start : end + 1]
    try:
        return PageRanges.model_validate_json(raw)
    except (ValidationError, ValueError):
        pass
    try:
        single = PageRange.model_validate_json(raw)
        return PageRanges(ranges=[single], rationale="(single-range response)")
    except (ValidationError, ValueError) as exc:
        raise ValueError(f"Scout returned an invalid page-range payload: {text!r}") from exc
