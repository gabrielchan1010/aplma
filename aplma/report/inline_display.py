"""IPython.display helpers for the per-stage notebook output.

Each helper takes one of the stage result dataclasses from `review_session`
and returns an ``IPython.display.HTML`` object the notebook can render inline.
The visual language mirrors the final report so the notebook + downloadable
HTML feel consistent.

CSS is scoped under ``.aplma`` to avoid bleeding into the rest of the notebook.
"""
from __future__ import annotations

import html
import json
from typing import Any

try:
    from IPython.display import HTML
except ImportError:  # pragma: no cover — Colab/Jupyter always provide this
    class HTML:  # type: ignore[no-redef]
        def __init__(self, data: str):
            self.data = data
        def _repr_html_(self) -> str:
            return self.data


_CSS = """
<style>
.aplma { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         color: #1a1a1a; line-height: 1.55; font-size: .88rem; }
.aplma .card { background: white; border: 1px solid #e5e7eb; border-radius: 8px;
               padding: 1rem 1.25rem; margin: .5rem 0; }
.aplma h4 { font-size: .95rem; font-weight: 700; margin: 0 0 .5rem;
            color: #0f0f23; letter-spacing: -.005em; }
.aplma .kv { display: grid; grid-template-columns: max-content 1fr;
             gap: .25rem 1.25rem; font-size: .85rem; }
.aplma .kv .k { font-weight: 600; color: #666; }
.aplma table { width: 100%; border-collapse: collapse; font-size: .82rem;
               margin-top: .4rem; }
.aplma th { background: #f8f8f8; padding: .4rem .65rem; text-align: left;
            font-weight: 600; border-bottom: 2px solid #e5e5e5; }
.aplma td { padding: .35rem .65rem; border-bottom: 1px solid #f0f0f0;
            vertical-align: top; }
.aplma tr:hover td { background: #fafafa; }
.aplma pre { background: #0f0f23; color: #c9d1d9; padding: .75rem 1rem;
             border-radius: 6px; font-size: .76rem; overflow-x: auto;
             white-space: pre-wrap; word-break: break-word; line-height: 1.5;
             margin: .4rem 0; }
.aplma .pill { display: inline-block; padding: .15rem .55rem; border-radius: 10px;
               font-size: .7rem; font-weight: 700; letter-spacing: .03em;
               text-transform: uppercase; }
.aplma .pill.success { background: #dcfce7; color: #15803d; }
.aplma .pill.failed  { background: #fee2e2; color: #b91c1c; }
.aplma .pill.llm     { background: #ede9fe; color: #6d28d9; }
.aplma .pill.py,
.aplma .pill.python  { background: #e0f2fe; color: #0369a1; }
.aplma .grounding { display: inline-block; padding: .12rem .5rem; border-radius: 10px;
                    font-size: .7rem; font-weight: 700; }
.aplma .grounding.matched     { background: #dcfce7; color: #15803d; }
.aplma .grounding.paraphrased { background: #fef3c7; color: #92400e; }
.aplma .grounding.ungrounded  { background: #fee2e2; color: #b91c1c; }
.aplma details { background: #f9fafb; border: 1px solid #e5e7eb;
                 border-radius: 6px; padding: .5rem .75rem; margin-top: .5rem; }
.aplma details > summary { cursor: pointer; font-weight: 600; font-size: .82rem;
                           color: #444; user-select: none; }
.aplma details[open] > summary { margin-bottom: .5rem; }
.aplma .note { background: #fffbeb; border-left: 3px solid #f59e0b;
               padding: .5rem .85rem; font-size: .82rem; border-radius: 0 4px 4px 0;
               margin: .4rem 0; }
.aplma .note.error { background: #fef2f2; border-color: #dc2626; color: #7f1d1d; }
.aplma .evidence { background: #f9fafb; border-left: 3px solid #7c3aed;
                   padding: .55rem .85rem; border-radius: 0 4px 4px 0;
                   margin: .35rem 0; font-size: .78rem;
                   font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
                   white-space: pre-wrap; word-break: break-word; }
.aplma .evidence mark { background: #fde68a; padding: 0 .15rem; border-radius: 2px; }
.aplma code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
              font-size: .82em; background: #f1f5f9; padding: .05rem .3rem;
              border-radius: 3px; }
</style>
"""


def _h(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _wrap(body: str) -> HTML:
    return HTML(_CSS + f'<div class="aplma">{body}</div>')


def _grounding_pill(g: Any) -> str:
    if g is None:
        return '<span class="grounding ungrounded">? ungrounded</span>'
    if getattr(g, "matched", False):
        return '<span class="grounding matched">✓ matched</span>'
    return '<span class="grounding paraphrased">~ paraphrased</span>'


# ── Stage renderers ───────────────────────────────────────────────────────────

def document_state_html(doc) -> HTML:
    heading_rows = "".join(
        f"<tr><td style='text-align:right;color:#888'>{_h(h.get('page_number', ''))}</td>"
        f"<td style='color:#888'>{_h(h.get('level', ''))}</td>"
        f"<td>{_h(h.get('text', ''))}</td></tr>"
        for h in doc.headings
    )
    heading_table = (
        "<details open style='margin-top:.5rem'>"
        f"<summary style='cursor:pointer;font-size:.82rem;color:#555'>"
        f"{len(doc.headings)} Docling headings</summary>"
        "<table style='margin-top:.4rem'>"
        "<thead><tr><th style='text-align:right'>Page</th>"
        "<th>Level</th><th>Heading text</th></tr></thead>"
        f"<tbody>{heading_rows}</tbody></table>"
        "</details>"
    ) if doc.headings else ""

    body = (
        '<div class="card">'
        f"<h4>Step 1 — Ingested <code>{_h(doc.document_name)}</code></h4>"
        '<div class="kv">'
        f'<div class="k">Document ID</div><div><code>{_h(doc.document_id)}</code></div>'
        f'<div class="k">Page offset</div><div>{_h(doc.page_offset)} '
        f'<span style="color:#888">(physical page = document page + {_h(doc.page_offset)})</span></div>'
        f'<div class="k">Docling headings</div><div>{_h(len(doc.headings))}{heading_table}</div>'
        "</div>"
        "</div>"
    )
    return _wrap(body)


def toc_html(toc) -> HTML:
    if not toc.entries:
        return _wrap(
            '<div class="card"><h4>Step 2 — Vision TOC</h4>'
            '<div class="note error">Vision TOC returned no entries.</div></div>'
        )
    rows = "".join(
        f"<tr><td><code>{_h(e.get('number', ''))}</code></td>"
        f"<td>{_h(e.get('title', ''))}</td>"
        f"<td style='text-align:right'>{_h(e.get('page', ''))}</td></tr>"
        for e in toc.entries
    )
    body = (
        '<div class="card">'
        f"<h4>Step 2 — Vision TOC <span class='pill llm'>LLM</span></h4>"
        f"<div style='color:#666;font-size:.82rem;margin-bottom:.4rem'>"
        f"Extracted {len(toc.entries)} clauses from the table of contents.</div>"
        "<table><thead><tr><th>Clause</th><th>Title</th><th>Page</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        "</div>"
    )
    return _wrap(body)


def scout_html(scout) -> HTML:
    header = (
        f"<h4>Step 3 — Scout: {_h(scout.covenant_type)} "
        f"<span class='pill llm'>LLM</span></h4>"
    )
    if scout.error is not None:
        body = (
            '<div class="card">' + header
            + f'<div class="note error"><strong>Scout failed:</strong> '
            f'{_h(type(scout.error).__name__)}: {_h(scout.error)}</div>'
            + _trace_details(scout.trace)
            + "</div>"
        )
        return _wrap(body)

    ranges = scout.ranges
    rationale = scout.rationale
    if ranges:
        rows = "".join(
            f"<tr><td><code>{_h(r.get('label', '—'))}</code></td>"
            f"<td style='text-align:right'>{_h(r['start_page'])}</td>"
            f"<td style='text-align:right'>{_h(r['end_page'])}</td>"
            f"<td style='text-align:right'>{_h(r['end_page'] - r['start_page'] + 1)}</td></tr>"
            for r in ranges
        )
        ranges_html = (
            "<table><thead><tr><th>label</th>"
            "<th style='text-align:right'>start</th>"
            "<th style='text-align:right'>end</th>"
            "<th style='text-align:right'>pages</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    else:
        ranges_html = '<div class="note">Scout returned no ranges.</div>'

    rationale_html = (
        f'<details><summary>Why these pages? (rationale)</summary>'
        f"<div style='margin-top:.4rem;font-size:.85rem;color:#444'>{_h(rationale)}</div>"
        "</details>" if rationale else ""
    )

    body = (
        '<div class="card">' + header
        + f"<div style='color:#666;font-size:.82rem;margin-bottom:.4rem'>"
        f"Scout made {len(scout.trace)} tool call(s) and identified "
        f"{len(ranges)} page range(s).</div>"
        + ranges_html + rationale_html + _trace_details(scout.trace)
        + "</div>"
    )
    return _wrap(body)


def _trace_details(trace: list[dict]) -> str:
    if not trace:
        return ""
    items: list[str] = []
    for i, call in enumerate(trace, start=1):
        args_json = _h(json.dumps(call.get("args", {}), indent=2))
        if "result" in call:
            result_json = _h(json.dumps(call["result"], indent=2, default=str))
            result_block = f"<pre>{result_json}</pre>"
        else:
            result_block = (
                f"<div style='color:#666;font-size:.8rem'>"
                f"→ {_h(call.get('result_chars', 0))} chars of page text</div>"
            )
        items.append(
            f"<div style='margin-bottom:.5rem'>"
            f"<div style='font-weight:600;font-size:.82rem'>{i}. "
            f"<code>{_h(call['tool'])}</code></div>"
            f"<pre>{args_json}</pre>{result_block}</div>"
        )
    return (
        f"<details><summary>Show tool-call trace ({len(trace)} call(s))</summary>"
        f"<div style='margin-top:.5rem'>{''.join(items)}</div>"
        "</details>"
    )


def slice_html(slice_) -> HTML:
    header = (
        f"<h4>Step 4 — Slicer: {_h(slice_.covenant_type)} "
        f"<span class='pill py'>Python</span></h4>"
    )
    if slice_.error is not None:
        body = (
            '<div class="card">' + header
            + f'<div class="note error"><strong>Slicer failed:</strong> '
            f'{_h(type(slice_.error).__name__)}: {_h(slice_.error)}</div>'
            "</div>"
        )
        return _wrap(body)
    if not slice_.slice_content:
        body = (
            '<div class="card">' + header
            + '<div class="note error">No slice content '
            "(Scout returned no ranges).</div></div>"
        )
        return _wrap(body)

    total_pages = sum(r["end_page"] - r["start_page"] + 1 for r in slice_.ranges)
    preview = slice_.slice_content[:500]
    suffix = "\n\n…" if len(slice_.slice_content) > 500 else ""

    body = (
        '<div class="card">' + header
        + '<div class="kv">'
        + f'<div class="k">Ranges</div><div>{len(slice_.ranges)} '
          f'covering {total_pages} page(s)</div>'
        + f'<div class="k">Slice length</div><div>{len(slice_.slice_content):,} chars</div>'
        + f'<div class="k">char→page entries</div><div>{len(slice_.page_map):,}</div>'
        + "</div>"
        + "<details><summary>Preview first 500 chars</summary>"
        + f"<pre>{_h(preview + suffix)}</pre></details>"
        + "</div>"
    )
    return _wrap(body)


def structural_extraction_html(session) -> HTML:
    header = (
        f"<h4>Step 5 — Structural Extraction: {_h(session.spec.covenant_type)} "
        f"<span class='pill python'>PYTHON</span></h4>"
    )
    if session.extract_error is not None and session.rule is None:
        body = (
            '<div class="card">' + header
            + f'<div class="note error"><strong>Structural extraction failed:</strong> '
            f'{_h(type(session.extract_error).__name__)}: '
            f'{_h(session.extract_error)}</div></div>'
        )
        return _wrap(body)
    if session.rule is None:
        body = (
            '<div class="card">' + header
            + '<div class="note error">No rule extracted.</div></div>'
        )
        return _wrap(body)

    rule = session.rule
    rows: list[str] = []

    fi_def = getattr(rule, "fi_definition", None)
    if fi_def is not None:
        rows.append(_extraction_row(
            cls=fi_def.__class__.__name__,
            label=getattr(fi_def, "clause_ref", "") or "—",
            text=_collapse_ws((getattr(fi_def, "definition_text", "") or ""))[:240],
            grounding=getattr(fi_def, "grounding", None),
            slice_content=session.slice_content,
        ))

    restriction = getattr(rule, "restriction", None)
    if restriction is not None:
        rows.append(_extraction_row(
            cls=restriction.__class__.__name__,
            label=getattr(restriction, "clause_ref", "") or "—",
            text=_collapse_ws((getattr(restriction, "restriction_text", "") or ""))[:240],
            grounding=getattr(restriction, "grounding", None),
            slice_content=session.slice_content,
        ))

    carve_outs = getattr(rule, "permitted_carve_outs", []) or []
    for carve in carve_outs:
        rows.append(_extraction_row(
            cls=carve.__class__.__name__,
            label="—",
            text=_carve_summary(carve),
            grounding=getattr(carve, "grounding", None),
            slice_content=session.slice_content,
        ))

    table = (
        "<table><thead><tr><th>class</th><th>clause</th><th>text</th>"
        "<th>grounding</th><th style='text-align:right'>page</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )

    json_block = (
        "<details><summary>Show raw JSON</summary>"
        f"<pre>{_h(rule.model_dump_json(indent=2))}</pre>"
        "</details>"
    )

    body = (
        '<div class="card">' + header
        + f"<div style='color:#666;font-size:.82rem;margin-bottom:.4rem'>"
        f"{len(carve_outs)} carve-out(s) extracted.</div>"
        + table + json_block
        + "</div>"
    )
    return _wrap(body)


def _extraction_row(*, cls: str, label: str, text: str,
                    grounding: Any, slice_content: str) -> str:
    page = getattr(grounding, "page_number", "—") if grounding else "—"
    evidence = _evidence_panel(grounding, slice_content)
    return (
        f"<tr><td><code>{_h(cls)}</code></td>"
        f"<td><code>{_h(label)}</code></td>"
        f"<td>{_h(text)}{evidence}</td>"
        f"<td>{_grounding_pill(grounding)}</td>"
        f"<td style='text-align:right'>{_h(page)}</td></tr>"
    )


def _evidence_panel(grounding: Any, slice_content: str) -> str:
    if grounding is None or not getattr(grounding, "matched", False):
        return ""
    start = getattr(grounding, "char_start", None)
    end = getattr(grounding, "char_end", None)
    if start is None or end is None or not slice_content:
        return ""
    pad = 80
    ws = max(0, int(start) - pad)
    we = min(len(slice_content), int(end) + pad)
    before = slice_content[ws:int(start)]
    middle = slice_content[int(start):int(end)]
    after = slice_content[int(end):we]
    prefix = "… " if ws > 0 else ""
    suffix = " …" if we < len(slice_content) else ""
    return (
        '<div class="evidence">'
        f"{_h(prefix)}{_h(before)}<mark>{_h(middle)}</mark>{_h(after)}{_h(suffix)}"
        "</div>"
    )


def _carve_summary(carve: Any) -> str:
    raw = (getattr(carve, "carve_out_text", "") or "").strip()
    return _collapse_ws(raw) if raw else "—"


def _collapse_ws(text: str) -> str:
    """Collapse Docling whitespace artefacts for display only. Verbatim text on
    the model is preserved; this only normalises what we render."""
    return " ".join(text.split())


__all__ = [
    "document_state_html",
    "toc_html",
    "scout_html",
    "slice_html",
    "structural_extraction_html",
]
