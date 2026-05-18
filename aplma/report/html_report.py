"""Self-contained HTML renderer for the multi-covenant review report.

Progressive-disclosure layout: the lawyer-relevant content (final extractions,
source evidence) sits at the top of each covenant tab; developer detail
(Scout trace, Slicer detail, structural parser diagnostics, raw JSON) is collapsed
behind ``<details>`` summaries below.

Returns one ``<html>`` string — no remote CSS/JS, no external assets.
"""
from __future__ import annotations

import base64
import datetime as _dt
import html
import io
import json
from typing import Any

from aplma.report.review_session import ReviewSession
from aplma.store.document_store import get_document_path


# ── Styling ───────────────────────────────────────────────────────────────────

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --ink: #14142b;
  --muted: #6b7280;
  --line: #e5e7eb;
  --bg: #fafbfc;
  --card: #ffffff;
  --accent: #7c3aed;
  --serif: 'Charter', 'Iowan Old Style', 'Georgia', serif;
  --sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', sans-serif;
  --mono: ui-monospace, SFMono-Regular, 'Menlo', 'Consolas', monospace;
}
html { scroll-behavior: smooth; }
body {
  font-family: var(--sans);
  background: var(--bg); color: var(--ink); line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}

/* ── Header bar — sticky ───────────────────────────────────────────────── */
.topbar {
  position: sticky; top: 0; z-index: 10;
  background: #0f0f23; color: #fff;
  padding: 1.1rem 2rem .9rem;
  box-shadow: 0 1px 12px rgba(0,0,0,.08);
}
.topbar-row {
  max-width: 1100px; margin: 0 auto;
  display: flex; align-items: baseline; gap: 1.5rem; flex-wrap: wrap;
}
.topbar h1 { font-size: 1.05rem; font-weight: 700; letter-spacing: -.005em; }
.topbar .meta { font-size: .78rem; color: #a8a8c0; }
.topbar .meta span + span { margin-left: 1rem; }

.tabs {
  max-width: 1100px; margin: .85rem auto 0;
  display: flex; gap: .25rem; flex-wrap: wrap;
}
.tab {
  padding: .55rem 1rem; font: 600 .82rem/1 var(--sans); color: #d0d0e0;
  background: transparent; border: 0; cursor: pointer;
  border-bottom: 3px solid transparent;
  display: flex; align-items: center; gap: .55rem;
  user-select: none; letter-spacing: .005em;
}
.tab:hover { color: #fff; }
.tab.active { color: #fff; border-bottom-color: var(--accent); }
.tab .dot { width: .55rem; height: .55rem; border-radius: 50%; }
.tab .dot.success { background: #22c55e; }
.tab .dot.warning { background: #f59e0b; }
.tab .dot.failed  { background: #ef4444; }

/* ── Page container ────────────────────────────────────────────────────── */
.container { max-width: 1100px; margin: 0 auto; padding: 1.75rem 1.5rem 4rem; }
.covenant { display: none; }
.covenant.active { display: block; }

/* ── Status banner ─────────────────────────────────────────────────────── */
.status {
  display: flex; align-items: center; gap: .85rem;
  padding: .85rem 1.25rem; border-radius: 8px;
  margin-bottom: 1.25rem; font-size: .85rem;
}
.status.success { background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }
.status.warning { background: #fffbeb; color: #92400e; border: 1px solid #fde68a; }
.status.failed  { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
.status strong { font-weight: 700; }

/* ── Cards ─────────────────────────────────────────────────────────────── */
.card {
  background: var(--card); border: 1px solid var(--line); border-radius: 10px;
  padding: 1.5rem 1.75rem; margin-bottom: 1.25rem;
}
.card h2 {
  font: 700 1.05rem/1.3 var(--sans); color: var(--ink);
  margin-bottom: .25rem; letter-spacing: -.005em;
}
.card h2 .sub {
  font-weight: 500; font-size: .82rem; color: var(--muted);
  margin-left: .6rem;
}
.card .lede {
  font: 400 .85rem/1.6 var(--sans); color: var(--muted);
  margin-bottom: 1rem;
}

/* ── Extraction body (serif) ───────────────────────────────────────────── */
.rule-body {
  font: 400 1rem/1.65 var(--serif);
  color: var(--ink);
  padding: .85rem 1.1rem; background: #faf9f6;
  border-left: 3px solid var(--accent); border-radius: 0 6px 6px 0;
  margin-bottom: 1.25rem;
}
.rule-body .ref {
  display: block; font: 600 .75rem/1 var(--sans);
  color: var(--accent); letter-spacing: .04em;
  text-transform: uppercase; margin-bottom: .35rem;
}
.rule-body pre.verbatim {
  font: 400 .95rem/1.55 var(--serif);
  color: var(--ink);
  background: transparent; border: none; padding: 0; margin: 0;
  white-space: pre-wrap; word-wrap: break-word;
}

/* ── Carve-outs ────────────────────────────────────────────────────────── */
.carveouts { list-style: none; counter-reset: cov-counter; }
.carveouts li {
  counter-increment: cov-counter;
  padding: .85rem 1rem .85rem 2.5rem; position: relative;
  border-top: 1px solid var(--line);
}
.carveouts li:first-child { border-top: 0; padding-top: .25rem; }
.carveouts li::before {
  content: counter(cov-counter) ".";
  position: absolute; left: 1rem; top: .85rem;
  font: 600 .85rem/1 var(--sans); color: var(--muted);
}
.carveouts li:first-child::before { top: .25rem; }
.carveouts .summary {
  font: 500 .92rem/1.55 var(--sans); color: var(--ink);
  margin-bottom: .35rem;
}
.carveouts .meta {
  font: 400 .78rem/1.4 var(--sans); color: var(--muted);
  display: flex; gap: .85rem; flex-wrap: wrap; align-items: center;
}
.carveouts .quote {
  margin-top: .45rem; font: 400 .78rem/1.55 var(--mono);
  color: #4b5563; background: #f8fafc; border: 1px solid #eef2f7;
  border-radius: 6px; padding: .45rem .6rem;
  white-space: pre-wrap; word-break: break-word;
}

/* ── Grounding pills ───────────────────────────────────────────────────── */
.pill {
  display: inline-flex; align-items: center; gap: .3rem;
  padding: .15rem .55rem; border-radius: 12px;
  font: 700 .68rem/1 var(--sans);
  letter-spacing: .04em; text-transform: uppercase;
}
.pill.verbatim    { background: #dcfce7; color: #15803d; }
.pill.paraphrased { background: #fef3c7; color: #92400e; }
.pill.ungrounded  { background: #fee2e2; color: #b91c1c; }
.pill .icon { font-size: .85rem; }

/* ── Source evidence ───────────────────────────────────────────────────── */
.evidence-list { display: flex; flex-direction: column; gap: .85rem; }
.evidence-row {
  display: grid; grid-template-columns: 4rem 1fr; gap: 1rem;
  align-items: start;
}
.evidence-row .page-ref {
  font: 600 .75rem/1.2 var(--sans); color: var(--muted);
  text-transform: uppercase; letter-spacing: .04em;
  padding-top: .35rem;
}
.evidence-row .page-ref small { display: block; font-weight: 400; opacity: .7; }
.evidence-text {
  font: 400 .85rem/1.65 var(--mono);
  background: #fafafa; border: 1px solid var(--line);
  padding: .65rem .85rem; border-radius: 6px;
  white-space: pre-wrap; word-break: break-word;
  color: #3d3d52;
}
.evidence-text mark {
  background: #fef08a; color: var(--ink);
  padding: 0 .15rem; border-radius: 2px; font-weight: 500;
}
.evidence-text .ellipsis { color: #cbd5e1; }
.manual-review {
  background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px;
  padding: .55rem .85rem; font: 400 .82rem/1.5 var(--sans); color: #92400e;
}
.compare-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: .75rem; margin-top: .55rem;
}
.compare-col {
  background: #f8fafc; border: 1px solid var(--line); border-radius: 6px; overflow: hidden;
}
.compare-col .label {
  display: block; padding: .35rem .55rem; font: 700 .68rem/1 var(--sans);
  letter-spacing: .04em; text-transform: uppercase; color: var(--muted);
  background: #f1f5f9; border-bottom: 1px solid var(--line);
}
.compare-col pre {
  margin: 0; border-radius: 0; background: #f8fafc; color: #374151;
  font-size: .74rem; line-height: 1.5;
}
@media (max-width: 900px) {
  .compare-grid { grid-template-columns: 1fr; }
}

.jump-link {
  display: inline-block; margin-left: .6rem; font-weight: 600;
  color: inherit; text-decoration: underline;
}
.snapshots-toggle summary {
  cursor: pointer; font: 600 .84rem/1 var(--sans); color: var(--accent);
  user-select: none;
}
.snapshots-toggle[open] summary { margin-bottom: .85rem; }

/* ── Source page snapshots (carousel) ───────────────────────────────────── */
.page-carousel {
  position: relative; max-width: 100%;
}
.page-shot {
  display: none;  /* hidden by default; .is-active makes one visible */
  border: 1px solid var(--line); border-radius: 8px; overflow: hidden;
  background: #f8fafc;
}
.page-shot.is-active {
  display: block;
}
.page-shot-header {
  display: flex; justify-content: space-between; gap: .75rem;
  padding: .6rem .85rem; border-bottom: 1px solid var(--line);
  font: 600 .85rem/1.3 var(--sans); color: var(--ink);
}
.page-shot-header span:last-child {
  color: var(--muted); font-weight: 500; text-align: right;
}
.page-shot img {
  width: 100%; height: auto; display: block; background: white;
}
.page-shot:target {
  /* Highlight when scrolled to via #page-snap-N anchor */
  outline: 3px solid var(--accent); outline-offset: 2px;
}

.page-carousel-nav {
  display: flex; align-items: center; justify-content: space-between;
  gap: .75rem; margin-top: .85rem; padding: .5rem .25rem;
}
.page-carousel-btn {
  font: 500 .85rem/1 var(--sans); color: var(--accent);
  background: #eef2ff; border: 1px solid #c7d2fe; border-radius: 6px;
  padding: .5rem .9rem; cursor: pointer; user-select: none;
}
.page-carousel-btn:hover:not(:disabled) {
  background: var(--accent); color: white; border-color: var(--accent);
}
.page-carousel-btn:disabled {
  opacity: .4; cursor: not-allowed;
}
.page-carousel-counter {
  font: 600 .85rem/1 var(--sans); color: var(--muted);
}

/* ── Inline page-jump badge (anchors to a #page-snap-N snapshot) ───────── */
.page-link {
  display: inline-block; margin-left: .4rem;
  padding: .1rem .5rem; border-radius: 999px;
  background: #eef2ff; color: var(--accent);
  font: 500 .72rem/1.4 var(--sans); text-decoration: none;
  vertical-align: middle; white-space: nowrap;
}
.page-link:hover {
  background: var(--accent); color: white;
}

/* ── JSON inline toggle ────────────────────────────────────────────────── */
.json-toggle {
  margin-top: 1rem; padding-top: .85rem; border-top: 1px dashed var(--line);
}
.json-toggle summary {
  cursor: pointer; font: 600 .8rem/1 var(--sans); color: var(--accent);
  user-select: none; display: inline-block;
}
.json-toggle summary:hover { text-decoration: underline; }
.json-toggle[open] summary { margin-bottom: .65rem; }
.json-toggle pre { margin-top: .5rem; }

/* ── Developer detail (collapsed sections) ─────────────────────────────── */
.dev-section {
  margin-top: 2rem;
}
.dev-section .label {
  font: 600 .68rem/1 var(--sans); color: var(--muted);
  letter-spacing: .12em; text-transform: uppercase;
  margin-bottom: .65rem;
}
details.dev {
  background: var(--card); border: 1px solid var(--line);
  border-radius: 8px; margin-bottom: .65rem; overflow: hidden;
}
details.dev > summary {
  cursor: pointer; padding: .85rem 1.25rem;
  font: 600 .9rem/1.2 var(--sans); color: var(--ink);
  display: flex; align-items: center; gap: .65rem;
  user-select: none; list-style: none;
}
details.dev > summary::-webkit-details-marker { display: none; }
details.dev > summary::before {
  content: '▸'; color: var(--muted); font-size: .75rem; flex-shrink: 0;
}
details.dev[open] > summary::before { content: '▾'; }
details.dev > summary:hover { background: #f9fafb; }
details.dev > summary .badge {
  font: 700 .68rem/1 var(--sans); padding: .2rem .55rem;
  border-radius: 10px; margin-left: auto;
  letter-spacing: .04em; text-transform: uppercase;
}
details.dev > summary .badge.llm { background: #ede9fe; color: #6d28d9; }
details.dev > summary .badge.py  { background: #e0f2fe; color: #0369a1; }
details.dev > summary .badge.err { background: #fee2e2; color: #b91c1c; }
.dev-body { padding: 0 1.25rem 1.25rem; }

/* ── Tables ────────────────────────────────────────────────────────────── */
table { width: 100%; border-collapse: collapse; font-size: .82rem;
        margin-top: .65rem; }
th { background: #f8fafc; padding: .5rem .7rem; text-align: left;
     font-weight: 600; border-bottom: 2px solid var(--line);
     font-size: .76rem; color: var(--muted);
     text-transform: uppercase; letter-spacing: .04em; }
td { padding: .45rem .7rem; border-bottom: 1px solid #f1f5f9;
     vertical-align: top; font-size: .82rem; }
tr:hover td { background: #fafafa; }

/* ── Code / prompt blocks ──────────────────────────────────────────────── */
pre { background: #0f0f23; color: #c9d1d9; padding: .85rem 1.1rem;
      border-radius: 6px; font: 400 .76rem/1.55 var(--mono);
      overflow-x: auto; white-space: pre-wrap; word-break: break-word;
      margin-top: .55rem; }
code { font: .85em var(--mono); background: #f1f5f9;
       padding: .05rem .3rem; border-radius: 3px; color: #3730a3; }
h3 { font: 600 .82rem/1.4 var(--sans); color: var(--ink);
     margin: 1rem 0 .45rem; }
h3:first-child { margin-top: 0; }
.prompt-box { border-radius: 6px; overflow: hidden; margin-top: .65rem; }
.prompt-role { padding: .3rem .85rem; font: 700 .7rem/1 var(--sans);
               letter-spacing: .06em; text-transform: uppercase; }
.prompt-role.system   { background: #374151; color: #d1d5db; }
.prompt-role.user     { background: #7c3aed; color: white; }
.prompt-role.response { background: #16a34a; color: white; }
.prompt-role.error    { background: #dc2626; color: white; }
.prompt-content { background: #0f0f23; color: #c9d1d9; padding: .85rem 1.1rem;
                  font: 400 .76rem/1.55 var(--mono);
                  white-space: pre-wrap; word-break: break-word; }
.note { background: #fffbeb; border-left: 3px solid #f59e0b;
        padding: .55rem .85rem; font-size: .82rem;
        border-radius: 0 4px 4px 0; margin-top: .55rem; }
.note.error { background: #fef2f2; border-color: #dc2626; color: #7f1d1d; }

/* ── Misc ──────────────────────────────────────────────────────────────── */
.empty {
  font: 400 .85rem/1.6 var(--sans); color: var(--muted);
  font-style: italic; padding: .5rem 0;
}
"""

JS = """
document.querySelectorAll('.tab').forEach(t => {
  t.addEventListener('click', () => {
    const target = t.dataset.target;
    document.querySelectorAll('.tab').forEach(x => {
      x.classList.remove('active');
      x.setAttribute('aria-selected', 'false');
    });
    document.querySelectorAll('.covenant').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    t.setAttribute('aria-selected', 'true');
    const el = document.getElementById(target);
    if (el) el.classList.add('active');
    window.scrollTo({top: 0, behavior: 'smooth'});
  });
});

// Page-snapshot carousels — one per covenant section.
// Each carousel: hidden .page-shot figures + Prev/Next buttons + page counter.
// Clicking a ↓ View page N anchor anywhere on the report jumps to and
// activates the matching slide.
document.querySelectorAll('[data-snapshot-carousel]').forEach(carousel => {
  const slides = Array.from(carousel.querySelectorAll('.page-shot'));
  if (!slides.length) return;
  const counter = carousel.querySelector('[data-snap-counter]');
  const prev = carousel.querySelector('[data-snap-prev]');
  const next = carousel.querySelector('[data-snap-next]');
  let idx = slides.findIndex(s => s.classList.contains('is-active'));
  if (idx < 0) idx = 0;

  function show(newIdx) {
    idx = Math.max(0, Math.min(slides.length - 1, newIdx));
    slides.forEach((s, i) => s.classList.toggle('is-active', i === idx));
    if (counter) {
      const pageNo = slides[idx].dataset.pageNumber;
      counter.textContent =
        (pageNo ? 'Page ' + pageNo + ' · ' : '') + (idx + 1) + ' of ' + slides.length;
    }
    if (prev) prev.disabled = (idx === 0);
    if (next) next.disabled = (idx === slides.length - 1);
  }

  if (prev) prev.addEventListener('click', () => show(idx - 1));
  if (next) next.addEventListener('click', () => show(idx + 1));

  // Initialise counter / disabled state on render
  show(idx);

  // Listen for clicks on any .page-link anchor — jump the carousel to that slide.
  // (Anchor's default behaviour also scrolls #page-snap-N into view, which still
  //  works because the active slide remains in the same DOM position.)
  document.querySelectorAll('.page-link').forEach(a => {
    const href = a.getAttribute('href') || '';
    if (!href.startsWith('#page-snap-')) return;
    a.addEventListener('click', () => {
      const targetId = href.slice(1);
      const i = slides.findIndex(s => s.id === targetId);
      if (i >= 0) show(i);
    });
  });

  // Also honour an initial #page-snap-N in the URL (e.g. shared deep links).
  if (window.location.hash.startsWith('#page-snap-')) {
    const i = slides.findIndex(s => s.id === window.location.hash.slice(1));
    if (i >= 0) show(i);
  }
});
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def h(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _clean_display(text: str) -> str:
    """Collapse Docling's PDF-extraction whitespace artefacts for display only.

    Runs of whitespace (often introduced by justified-text layout in the PDF,
    e.g. `'(c) any  amount  raised  pursuant to'`) collapse to single spaces.
    Preserves the underlying verbatim model field — this is *only* applied
    when rendering text to the lawyer's view.
    """
    if not text:
        return ""
    # Collapse all runs of whitespace (including \n, \t, multiple spaces) to single space.
    return " ".join(text.split())


def _clean_multiline_display(text: str) -> str:
    """Same as _clean_display but preserves line breaks between sub-items.

    Use for multi-line definitions where each `(a)`/`(b)` sub-paragraph should
    appear on its own visual line — but within each line, multi-spaces collapse.
    """
    if not text:
        return ""
    return "\n".join(" ".join(line.split()) for line in text.split("\n") if line.strip())


def _code_block(text: str) -> str:
    return f"<pre>{h(text)}</pre>"


def _prompt_block(role: str, content: str, style: str = "user") -> str:
    return (
        f'<div class="prompt-box"><div class="prompt-role {h(style)}">{h(role)}</div>'
        f'<div class="prompt-content">{h(content)}</div></div>'
    )


def _note(inner_html: str, error: bool = False) -> str:
    cls = "note error" if error else "note"
    return f'<div class="{cls}">{inner_html}</div>'


def _grounding_pill(g: Any) -> str:
    if g is None:
        return '<span class="pill ungrounded"><span class="icon">?</span>ungrounded</span>'
    if getattr(g, "verbatim", False):
        return '<span class="pill verbatim"><span class="icon">✓</span>verbatim</span>'
    return '<span class="pill paraphrased"><span class="icon">~</span>paraphrased</span>'


def _grounding_label(g: Any) -> str:
    if g is None:
        return "ungrounded"
    if getattr(g, "verbatim", False):
        return "verbatim"
    return "paraphrased"


def _groundings_for_review(session: ReviewSession) -> list[Any]:
    rule = session.rule
    if rule is None:
        return []
    groundings: list[Any] = []
    for comp in (getattr(rule, "fi_definition", None), getattr(rule, "restriction", None)):
        if comp is not None:
            groundings.append(getattr(comp, "grounding", None))
    groundings.extend(
        getattr(carve, "grounding", None)
        for carve in getattr(rule, "permitted_carve_outs", []) or []
    )
    return groundings


def _needs_manual_review(grounding: Any) -> bool:
    if grounding is None:
        return True
    if not getattr(grounding, "verbatim", False):
        return True
    return (
        getattr(grounding, "char_start", None) is None
        or getattr(grounding, "char_end", None) is None
    )


def _review_counts(session: ReviewSession) -> dict[str, int]:
    groundings = _groundings_for_review(session)
    needs_review = sum(1 for g in groundings if _needs_manual_review(g))
    return {
        "total": len(groundings),
        "verbatim": len(groundings) - needs_review,
        "needs_review": needs_review,
    }


def _tab_state(session: ReviewSession) -> str:
    if session.failed_stage:
        return "failed"
    if _review_counts(session)["needs_review"]:
        return "warning"
    return "success"


def _source_pages(session: ReviewSession) -> list[int]:
    pages: set[int] = set()
    for grounding in _groundings_for_review(session):
        page = getattr(grounding, "page_number", None) if grounding is not None else None
        if isinstance(page, int) and page > 0:
            pages.add(page)
    return sorted(pages)


def _page_snapshot_data_uri(document_id: str, page_no: int) -> str | None:
    try:
        import pypdfium2 as pdfium

        pdf_path = get_document_path(document_id)
        pdf = pdfium.PdfDocument(str(pdf_path))
        if page_no < 1 or page_no > len(pdf):
            return None

        bitmap = pdf[page_no - 1].render(scale=120 / 72)
        buf = io.BytesIO()
        bitmap.to_pil().save(buf, format="PNG", optimize=True)
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception:
        return None


# ── Top-half: lawyer-first content ────────────────────────────────────────────

def _render_final_extraction(session: ReviewSession) -> str:
    rule = session.rule
    if rule is None:
        if session.extract_error is not None:
            return (
                '<section class="card">'
                f'<h2>Final Extraction <span class="sub">'
                f'{h(session.spec.covenant_type)}</span></h2>'
                + _note(
                    f"<strong>Extraction failed:</strong> "
                    f"{h(type(session.extract_error).__name__)}: "
                    f"{h(session.extract_error)}",
                    error=True,
                )
                + "</section>"
            )
        if session.scout_error is not None:
            return (
                '<section class="card">'
                f'<h2>Final Extraction <span class="sub">'
                f'{h(session.spec.covenant_type)}</span></h2>'
                + _note(
                    "Cannot extract — Scout failed to identify the relevant "
                    "page range. See <em>How we found this</em> below.",
                    error=True,
                )
                + "</section>"
            )
        return (
            '<section class="card">'
            f'<h2>Final Extraction <span class="sub">'
            f'{h(session.spec.covenant_type)}</span></h2>'
            + _note(
                "No structured extraction was produced. Expand the pipeline "
                "detail below to inspect the page ranges and prompts.",
                error=True,
            )
            + "</section>"
        )

    fi_def = getattr(rule, "fi_definition", None)
    restriction = getattr(rule, "restriction", None)
    carve_outs = getattr(rule, "permitted_carve_outs", []) or []

    def_ref = getattr(fi_def, "clause_ref", "") if fi_def else ""
    def_text = (getattr(fi_def, "definition_text", "") or "").strip() if fi_def else ""
    def_g = getattr(fi_def, "grounding", None) if fi_def else None

    res_ref = getattr(restriction, "clause_ref", "") if restriction else ""
    res_text = (getattr(restriction, "restriction_text", "") or "").strip() if restriction else ""
    res_g = getattr(restriction, "grounding", None) if restriction else None

    def_page_link = _page_jump_link(def_g)
    res_page_link = _page_jump_link(res_g)

    def_clean = _clean_multiline_display(def_text)
    res_clean = _clean_multiline_display(res_text)

    definition_body = (
        '<div class="rule-body">'
        '<div style="font-size:.85rem;color:#64748b;margin-bottom:.25rem">Definition of Financial Indebtedness</div>'
        + (f'<span class="ref">{h(def_ref)}</span>' if def_ref else "")
        + (
            f'<pre class="verbatim">{h(def_clean)}</pre>'
            if def_clean
            else '<em style="color:#94a3b8">No definition extracted — Docling did not detect the anchor on the Scout-selected pages. Check the Source Page Snapshots below for the expected location.</em>'
        )
        + (f' {_grounding_pill(def_g)}' if def_g is not None or def_text else "")
        + def_page_link
        + "</div>"
    )

    rule_body = (
        '<div class="rule-body">'
        '<div style="font-size:.85rem;color:#64748b;margin-bottom:.25rem">Restriction</div>'
        + (f'<span class="ref">{h(res_ref)}</span>' if res_ref else "")
        + (
            f'<pre class="verbatim">{h(res_clean)}</pre>'
            if res_clean
            else '<em style="color:#94a3b8">No restriction extracted — Docling did not detect a `N.M Financial Indebtedness` heading on the Scout-selected pages.</em>'
        )
        + (f' {_grounding_pill(res_g)}' if res_g is not None or res_text else "")
        + res_page_link
        + "</div>"
    )

    if carve_outs:
        carve_html = "".join(_render_carveout(c) for c in carve_outs)
        carveouts_block = (
            f'<h3>Permitted carve-outs <span style="color:#94a3b8;'
            f'font-weight:400">({len(carve_outs)})</span></h3>'
            f'<ul class="carveouts">{carve_html}</ul>'
        )
    else:
        carveouts_block = (
            '<h3>Permitted carve-outs</h3>'
            '<div class="empty">No carve-outs extracted.</div>'
        )

    json_toggle = (
        '<details class="json-toggle"><summary>View raw JSON</summary>'
        f"{_code_block(rule.model_dump_json(indent=2))}"
        "</details>"
    )

    return (
        '<section class="card">'
        f'<h2>Final Extraction <span class="sub">'
        f'{h(session.spec.covenant_type)}</span></h2>'
        + definition_body + rule_body + carveouts_block + json_toggle
        + "</section>"
    )


def _render_carveout(carve: Any) -> str:
    summary = _carve_summary(carve)
    g = getattr(carve, "grounding", None)
    page_link = _page_jump_link(g)
    return (
        "<li>"
        f'<div class="summary">{h(summary)}</div>'
        '<div class="meta">'
        f'{_grounding_pill(g)}'
        + page_link
        + "</div>"
        + "</li>"
    )


def _page_jump_link(grounding: Any) -> str:
    """Render an anchor badge that scrolls to the rendered PDF page snapshot."""
    page = getattr(grounding, "page_number", None) if grounding is not None else None
    if not isinstance(page, int) or page <= 0:
        return ""
    return (
        f'<a class="page-link" href="#page-snap-{page}" '
        f'title="Jump to rendered PDF page {h(page)}">↓ View page {h(page)}</a>'
    )


def _carve_summary(carve: Any) -> str:
    raw = (getattr(carve, "carve_out_text", "") or "").strip()
    return _clean_display(raw) if raw else "—"


def _render_source_evidence(session: ReviewSession, section_id: str) -> str:
    rule = session.rule
    if rule is None:
        return ""

    rows: list[tuple[bool, str]] = []
    fi_def = getattr(rule, "fi_definition", None)
    if fi_def is not None:
        def_g = getattr(fi_def, "grounding", None)
        rows.append((_needs_manual_review(def_g), _evidence_row(
            label=getattr(fi_def, "clause_ref", "") or "FI Definition",
            grounding=def_g,
            slice_content=session.slice_content,
            page_offset=session.page_offset,
            page_map=session.page_map,
            row_id=_row_id(section_id, "definition"),
        )))
    restriction = getattr(rule, "restriction", None)
    if restriction is not None:
        res_g = getattr(restriction, "grounding", None)
        rows.append((_needs_manual_review(res_g), _evidence_row(
            label=getattr(restriction, "clause_ref", "") or "Restriction",
            grounding=res_g,
            slice_content=session.slice_content,
            page_offset=session.page_offset,
            page_map=session.page_map,
            row_id=_row_id(section_id, "restriction"),
        )))
    for i, carve in enumerate(getattr(rule, "permitted_carve_outs", []) or [], start=1):
        grounding = getattr(carve, "grounding", None)
        rows.append((_needs_manual_review(grounding), _evidence_row(
            label=f"Carve-out {i}",
            grounding=grounding,
            slice_content=session.slice_content,
            page_offset=session.page_offset,
            page_map=session.page_map,
            row_id=_row_id(section_id, f"carve-{i}"),
        )))

    if not rows:
        return ""
    review_rows = [html for needs_review, html in rows if needs_review]
    ok_rows = [html for needs_review, html in rows if not needs_review]
    blocks: list[str] = []
    if review_rows:
        blocks.append(f'<h3 id="{section_id}-needs-manual-review">Needs Manual Review</h3>')
        blocks.append(f'<div class="evidence-list">{"".join(review_rows)}</div>')
    if ok_rows:
        blocks.append('<h3>Verbatim Grounded</h3>')
        blocks.append(f'<div class="evidence-list">{"".join(ok_rows)}</div>')

    return (
        '<section class="card">'
        + '<h2>Source Evidence</h2>'
        + '<div class="lede">Review flagged rows first. Verbatim rows are grouped '
        + 'separately for quick confirmation.</div>'
        + "".join(blocks)
        + "</section>"
    )


def _render_source_page_snapshots(session: ReviewSession) -> str:
    pages = _source_pages(session)
    if not pages:
        return ""

    cards: list[str] = []
    for idx, page in enumerate(pages):
        data_uri = _page_snapshot_data_uri(session.document_id, page)
        if data_uri is None:
            continue
        labels = _labels_for_page(session, page)
        active = " is-active" if idx == 0 else ""
        cards.append(
            f'<figure class="page-shot{active}" id="page-snap-{h(page)}" '
            f'data-page-number="{h(page)}" data-snap-index="{idx}">'
            '<figcaption class="page-shot-header">'
            f'<span>Page {h(page)}</span>'
            f'<span>{h(", ".join(labels))}</span>'
            '</figcaption>'
            f'<img src="{data_uri}" alt="Source PDF page {h(page)}">'
            '</figure>'
        )

    if not cards:
        return (
            '<section class="card">'
            '<h2>Source Page Snapshots</h2>'
            + _note(
                "Page snapshots are unavailable because the PDF rendering "
                "dependency is not installed in this runtime."
            )
            + "</section>"
        )

    nav = (
        '<nav class="page-carousel-nav" aria-label="Snapshot navigation">'
        '<button type="button" class="page-carousel-btn" data-snap-prev '
        'aria-label="Previous page">← Previous</button>'
        '<span class="page-carousel-counter" data-snap-counter aria-live="polite">'
        f'1 of {len(cards)}'
        '</span>'
        '<button type="button" class="page-carousel-btn" data-snap-next '
        'aria-label="Next page">Next →</button>'
        '</nav>'
    )

    return (
        '<section class="card">'
        '<h2>Source Page Snapshots</h2>'
        '<div class="lede">Rendered PDF pages for the grounded source evidence. '
        'Use the navigation below or click <strong>↓ View page N</strong> in '
        'any extraction above to jump to that page. '
        'These pages are the ground truth.</div>'
        f'<div class="page-carousel" data-snapshot-carousel>'
        f'{"".join(cards)}'
        f'{nav}'
        '</div>'
        "</section>"
    )


def _labels_for_page(session: ReviewSession, page: int) -> list[str]:
    rule = session.rule
    if rule is None:
        return []

    labels: list[str] = []
    fi_def = getattr(rule, "fi_definition", None)
    if fi_def is not None:
        def_g = getattr(fi_def, "grounding", None)
        if getattr(def_g, "page_number", None) == page:
            labels.append(getattr(fi_def, "clause_ref", "") or "FI Definition")
    restriction = getattr(rule, "restriction", None)
    if restriction is not None:
        res_g = getattr(restriction, "grounding", None)
        if getattr(res_g, "page_number", None) == page:
            labels.append(getattr(restriction, "clause_ref", "") or "Restriction")

    for i, carve in enumerate(getattr(rule, "permitted_carve_outs", []) or [], start=1):
        grounding = getattr(carve, "grounding", None)
        if getattr(grounding, "page_number", None) == page:
            labels.append(f"Carve-out {i}")
    return labels


def _slice_text_for_page(
    *,
    slice_content: str,
    page_map: list[tuple[int, int]],
    page_no: int,
) -> str:
    """Return the full text on `page_no` from the concatenated slice content.

    Docling emits each text/table item separately, so page_map has one entry per
    item — many entries can share the same page_no. We span from the first entry
    on the target page through the last consecutive entry on that page.
    """
    if not slice_content or not page_map or page_no < 1:
        return ""
    start: int | None = None
    for offset, pg in page_map:
        if pg == page_no:
            if start is None:
                start = offset
            continue
        if start is not None:
            # First entry past the target page → end of slice for that page
            return slice_content[start:offset].strip()
    if start is not None:
        return slice_content[start:].strip()
    return ""


def _find_in_text(needle: str, haystack: str) -> int | None:
    """Return the start position of needle (or its opening phrase) in haystack.

    Tries the first 60 characters, then the first 5 words, case-insensitively.
    Returns None when no match is found.
    """
    h_lower = haystack.lower()
    for probe in [
        " ".join(needle.split())[:60].lower(),
        " ".join(needle.split()[:5]).lower(),
    ]:
        if probe:
            pos = h_lower.find(probe)
            if pos != -1:
                return pos
    return None


def _windowed_page_text(model_text: str, page_text: str, window: int = 400) -> str:
    """Return a ±window-char excerpt of page_text anchored on model_text.

    Falls back to a truncated view from the top when no match is found.
    """
    if not page_text:
        return _code_block("No page text available for this page.")
    pos = _find_in_text(model_text, page_text)
    if pos is not None:
        ws = max(0, pos - window)
        we = min(len(page_text), pos + len(model_text) + window)
        prefix = "… " if ws > 0 else ""
        suffix = " …" if we < len(page_text) else ""
        return _code_block(prefix + page_text[ws:we] + suffix)
    truncated = page_text[:4000].rstrip() + ("\n\n… [truncated]" if len(page_text) > 4000 else "")
    return _code_block(truncated)


def _evidence_row(*, label: str, grounding: Any, slice_content: str,
                  page_offset: int, page_map: list[tuple[int, int]],
                  row_id: str) -> str:
    if grounding is None:
        return (
            f'<div class="evidence-row" id="{h(row_id)}">'
            f'<div class="page-ref">{h(label)}<small>—</small></div>'
            '<div class="manual-review">Ungrounded — needs manual review.</div>'
            '</div>'
        )
    page = getattr(grounding, "page_number", "—")
    if not getattr(grounding, "verbatim", False):
        ext = getattr(grounding, "extraction_text", "") or ""
        page_no = int(page) if isinstance(page, int) else -1
        page_text = _slice_text_for_page(
            slice_content=slice_content, page_map=page_map, page_no=page_no
        )
        compare = (
            '<div class="compare-grid">'
            '<div class="compare-col"><span class="label">Model reported text</span>'
            f'{_code_block(ext[:500])}</div>'
            '<div class="compare-col"><span class="label">Source page (around matched location)</span>'
            f'{_windowed_page_text(ext, page_text)}</div>'
            '</div>'
        )
        body = (
            '<div class="manual-review">'
            'Paraphrased — model text may not be verbatim. Full source page shown on the right for manual verification:'
            + compare
            + '</div>'
        )
        return (
            f'<div class="evidence-row" id="{h(row_id)}">'
            f'<div class="page-ref">{h(label)}<small>p. {h(page)}</small></div>'
            f'{body}</div>'
        )

    start = getattr(grounding, "char_start", None)
    end = getattr(grounding, "char_end", None)
    if start is None or end is None or not slice_content:
        return (
            f'<div class="evidence-row" id="{h(row_id)}">'
            f'<div class="page-ref">{h(label)}<small>p. {h(page)}</small></div>'
            '<div class="manual-review">No char interval — needs manual review.</div>'
            '</div>'
        )
    pad = 100
    ws = max(0, int(start) - pad)
    we = min(len(slice_content), int(end) + pad)
    before = slice_content[ws:int(start)]
    middle = slice_content[int(start):int(end)]
    after = slice_content[int(end):we]
    prefix = '<span class="ellipsis">… </span>' if ws > 0 else ""
    suffix = '<span class="ellipsis"> …</span>' if we < len(slice_content) else ""
    return (
        f'<div class="evidence-row" id="{h(row_id)}">'
        f'<div class="page-ref">{h(label)}<small>p. {h(page)}</small></div>'
        '<div class="evidence-text">'
        f'{prefix}{h(before)}<mark>{h(middle)}</mark>{h(after)}{suffix}'
        '</div>'
        '</div>'
    )


def _row_id(section_id: str, suffix: str) -> str:
    return f"{section_id}-evidence-{suffix}"


def _first_review_row_id(session: ReviewSession, section_id: str) -> str:
    rule = session.rule
    if rule is None:
        return f"{section_id}-needs-manual-review"
    fi_def = getattr(rule, "fi_definition", None)
    if fi_def is not None and _needs_manual_review(getattr(fi_def, "grounding", None)):
        return _row_id(section_id, "definition")
    restriction = getattr(rule, "restriction", None)
    if restriction is not None and _needs_manual_review(getattr(restriction, "grounding", None)):
        return _row_id(section_id, "restriction")
    for i, carve in enumerate(getattr(rule, "permitted_carve_outs", []) or [], start=1):
        if _needs_manual_review(getattr(carve, "grounding", None)):
            return _row_id(section_id, f"carve-{i}")
    return f"{section_id}-needs-manual-review"


# ── Bottom-half: developer detail (collapsed) ─────────────────────────────────

def _render_dev_section(session: ReviewSession) -> str:
    return (
        '<div class="dev-section">'
        '<div class="label">Pipeline detail · click to expand</div>'
        + _render_headings_details(session)
        + _render_scout_details(session)
        + _render_slicer_details(session)
        + _render_structural_extraction_details(session)
        + "</div>"
    )


def _render_headings_details(session: ReviewSession) -> str:
    headings = sorted(
        session.docling_headings,
        key=lambda h: (h.get("page_number", 0), h.get("level", 0)),
    )
    if not headings:
        return ""
    slice_pages: set[int] = {
        p
        for r in session.ranges
        for p in range(int(r.get("start_page", 0)), int(r.get("end_page", 0)) + 1)
    }
    rows = "".join(
        f"<tr{'  style=\"background:#f0fdf4\"' if hh.get('page_number') in slice_pages else ''}>"
        f"<td style='text-align:right'>{h(str(hh.get('page_number', '')))}</td>"
        f"<td>{h(str(hh.get('level', '')))}</td>"
        f"<td>{'&nbsp;' * (2 * (hh.get('level', 1) - 1))}{h(hh.get('text', ''))}</td></tr>"
        for hh in headings
    )
    return (
        '<details class="dev">'
        f'<summary>All Docling headings ({len(headings)})'
        f'<span class="badge py">PYTHON</span></summary>'
        '<div class="dev-body">'
        '<p style="font-size:.8rem;color:#666;margin:0 0 .5rem">Highlighted rows are on pages fetched by the Slicer.</p>'
        '<table><thead><tr>'
        '<th style="text-align:right">Page</th>'
        '<th>Level</th>'
        '<th>Heading text</th>'
        '</tr></thead>'
        f'<tbody>{rows}</tbody></table>'
        '</div></details>'
    )


def _render_scout_details(session: ReviewSession) -> str:
    badge_class = "err" if session.scout_error is not None else "llm"
    badge_text = "ERROR" if session.scout_error is not None else "LLM"
    title = "How we found this — Scout"
    body = _scout_body(session)
    return (
        '<details class="dev">'
        f'<summary>{h(title)}<span class="badge {badge_class}">{badge_text}</span></summary>'
        f'<div class="dev-body">{body}</div>'
        "</details>"
    )


def _scout_body(session: ReviewSession) -> str:
    if session.scout_error is not None:
        return _note(
            f"<strong>{h(type(session.scout_error).__name__)}:</strong> "
            f"{h(session.scout_error)}",
            error=True,
        )
    parts: list[str] = [
        _prompt_block("SYSTEM", session.scout_system_prompt, style="system"),
        _prompt_block("USER", session.scout_user_prompt, style="user"),
    ]
    if session.scout_trace:
        for i, call in enumerate(session.scout_trace, start=1):
            parts.append(f"<h3>Tool call {i} — {h(call['tool'])}</h3>")
            parts.append(_prompt_block(
                f"LLM → {call['tool']}",
                json.dumps({"arguments": call.get("args", {})}, indent=2),
            ))
            if "result" in call:
                parts.append(_prompt_block(
                    f"{call['tool']} result",
                    json.dumps(call["result"], indent=2, default=str),
                    style="response",
                ))
            else:
                parts.append(_prompt_block(
                    f"{call['tool']} result",
                    json.dumps({"chars": call.get("result_chars", 0)}, indent=2),
                    style="response",
                ))
    else:
        parts.append(_note("Scout returned without calling any tools."))

    parts.append("<h3>Scout final response</h3>")
    if session.scout_result is None:
        parts.append(_note("Scout did not return a result.", error=True))
        return "".join(parts)
    ranges = session.scout_result.get("ranges", [])
    rationale = session.scout_result.get("rationale", "")
    rows = "".join(
        f"<tr><td><code>{h(r.get('label', '—'))}</code></td>"
        f"<td style='text-align:right'>{h(r['start_page'])}</td>"
        f"<td style='text-align:right'>{h(r['end_page'])}</td>"
        f"<td style='text-align:right'>{h(r['end_page'] - r['start_page'] + 1)}</td></tr>"
        for r in ranges
    )
    parts.append(
        '<table><thead><tr><th>label</th><th style="text-align:right">start</th>'
        '<th style="text-align:right">end</th>'
        '<th style="text-align:right">pages</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    )
    if rationale:
        parts.append(_prompt_block("rationale", rationale, style="response"))
    return "".join(parts)


def _render_slicer_details(session: ReviewSession) -> str:
    title = "Source slice — Slicer"
    body = _slicer_body(session)
    return (
        '<details class="dev">'
        f'<summary>{h(title)}<span class="badge py">PYTHON</span></summary>'
        f'<div class="dev-body">{body}</div>'
        "</details>"
    )


def _slicer_body(session: ReviewSession) -> str:
    if not session.ranges and not session.slice_content:
        return _note("No slice content — Scout produced no ranges.")
    ranges_rows = "".join(
        f"<tr><td><code>{h(r.get('label', '—'))}</code></td>"
        f"<td style='text-align:right'>{h(r['start_page'])}</td>"
        f"<td style='text-align:right'>{h(r['end_page'])}</td>"
        f"<td style='text-align:right'>{h(r['end_page'] - r['start_page'] + 1)}</td></tr>"
        for r in session.ranges
    )
    preview = session.slice_content[:1500]
    truncated = "\n\n… [truncated]" if len(session.slice_content) > 1500 else ""
    page_map_rows = "".join(
        f"<tr><td style='text-align:right'>{h(cs)}</td>"
        f"<td style='text-align:right'>{h(pg)}</td></tr>"
        for cs, pg in session.page_map[:20]
    )
    pm_note = (
        f" (first 20 of {len(session.page_map):,})"
        if len(session.page_map) > 20 else ""
    )
    return (
        "<h3>Ranges fetched</h3>"
        '<table><thead><tr><th>label</th>'
        '<th style="text-align:right">start</th>'
        '<th style="text-align:right">end</th>'
        '<th style="text-align:right">pages</th></tr></thead>'
        f"<tbody>{ranges_rows}</tbody></table>"
        f"<h3>Concatenated content "
        f"(first {min(1500, len(session.slice_content)):,} of "
        f"{len(session.slice_content):,} chars)</h3>"
        f"{_code_block(preview + truncated)}"
        f"<h3>char → page map{pm_note}</h3>"
        '<table><thead><tr><th style="text-align:right">char_start</th>'
        '<th style="text-align:right">page</th></tr></thead>'
        f"<tbody>{page_map_rows}</tbody></table>"
    )


def _render_structural_extraction_details(session: ReviewSession) -> str:
    title = "Structural parser diagnostics"
    body = _structural_extraction_body(session)
    return (
        '<details class="dev">'
        f'<summary>{h(title)}<span class="badge py">PYTHON</span></summary>'
        f'<div class="dev-body">{body}</div>'
        "</details>"
    )


def _structural_extraction_body(session: ReviewSession) -> str:
    parts: list[str] = []

    # Docling headings for the sliced pages — these are what the parser can see.
    slice_pages: set[int] = set()
    for r in session.ranges:
        for p in range(int(r.get("start_page", 0)), int(r.get("end_page", 0)) + 1):
            slice_pages.add(p)
    slice_headings = sorted(
        [h for h in session.docling_headings if h.get("page_number") in slice_pages],
        key=lambda h: (h.get("page_number", 0), h.get("level", 0)),
    )
    if slice_headings:
        heading_rows = "".join(
            f"<tr><td>{h(str(hh.get('page_number', '')))}</td>"
            f"<td>{h(str(hh.get('level', '')))}</td>"
            f"<td>{h(hh.get('text', ''))}</td></tr>"
            for hh in slice_headings
        )
        parts.append(
            "<h3>Docling headings on sliced pages</h3>"
            "<table><thead><tr><th>Page</th><th>Level</th><th>Heading text</th></tr></thead>"
            f"<tbody>{heading_rows}</tbody></table>"
        )
    else:
        parts.append(_note("No Docling headings found on the sliced pages."))

    parts.append(_prompt_block("PARSER", session.structural_extraction_summary))
    if session.extract_error is not None:
        parts.append(_note(
            f"<strong>Structural extraction error:</strong> "
            f"{h(type(session.extract_error).__name__)}: "
            f"{h(session.extract_error)}",
            error=True,
        ))
    return "".join(parts)


# ── Covenant pane ─────────────────────────────────────────────────────────────

def _render_status_banner(session: ReviewSession, section_id: str) -> str:
    jump = (
        f'<a class="jump-link" href="#{_first_review_row_id(session, section_id)}">'
        'Jump to first review item</a>'
    )
    failed = session.failed_stage
    if failed is None:
        counts = _review_counts(session)
        if counts["needs_review"]:
            noun = "source match" if counts["needs_review"] == 1 else "source matches"
            verb = "needs" if counts["needs_review"] == 1 else "need"
            return (
                '<div class="status warning">'
                '<strong>Extraction completed with review items.</strong> '
                f'{counts["needs_review"]} {noun} {verb} manual review; '
                f'{counts["verbatim"]}/{counts["total"]} are verbatim-grounded.'
                + jump
                + '</div>'
            )
        return (
            '<div class="status success">'
            '<strong>Extraction completed.</strong> '
            f'All {_review_counts(session)["total"]} extracted source matches are verbatim-grounded.'
            '</div>'
        )
    label = {"scout": "Scout (page identification)",
             "structural_extraction": "Structural extraction"}.get(failed, failed)
    return (
        '<div class="status failed">'
        f'<strong>✗ {h(label)} failed.</strong> '
        'The other covenant may still have run successfully — switch tabs above. '
        'Expand the pipeline detail below for diagnostics.'
        + jump
        + '</div>'
    )


def _render_covenant(idx: int, session: ReviewSession) -> str:
    section_id = f"covenant-{idx}"
    active = "active" if idx == 0 else ""
    return (
        f'<section class="covenant {active}" id="{section_id}">'
        + _render_status_banner(session, section_id)
        + _render_final_extraction(session)
        + _render_source_evidence(session, section_id)
        + _render_source_page_snapshots(session)
        + _render_dev_section(session)
        + "</section>"
    )


# ── Public entry point ────────────────────────────────────────────────────────

def render_report(sessions: list[ReviewSession]) -> str:
    if not sessions:
        return _wrap_page(
            body_html=_note("No sessions to render.", error=True),
            doc_name="—", subtitle="empty report", tabs_html="",
        )

    tabs_html = "".join(
        f'<button class="tab{" active" if i == 0 else ""}" '
        f'data-target="covenant-{i}" type="button" role="tab" '
        f'aria-controls="covenant-{i}" aria-selected="{str(i == 0).lower()}">'
        f'{h(s.spec.covenant_type)}'
        f'<span class="dot {_tab_state(s)}"></span>'
        "</button>"
        for i, s in enumerate(sessions)
    )

    covenants_html = "".join(_render_covenant(i, s) for i, s in enumerate(sessions))

    n_ok = sum(1 for s in sessions if s.failed_stage is None)
    n_total = len(sessions)
    review_items = sum(_review_counts(s)["needs_review"] for s in sessions)
    review_text = (
        "all evidence verbatim-grounded"
        if review_items == 0
        else f"{review_items} source match{'es' if review_items != 1 else ''} need review"
    )
    subtitle = (
        f"{n_ok}/{n_total} covenant{'s' if n_total != 1 else ''} succeeded · "
        f"{review_text} · "
        f"page offset {sessions[0].page_offset} · "
        f"document {sessions[0].document_id[:12]} · "
        f"generated {_dt.datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )

    return _wrap_page(
        body_html=covenants_html,
        doc_name=sessions[0].document_name,
        subtitle=subtitle,
        tabs_html=tabs_html,
    )


def _wrap_page(*, body_html: str, doc_name: str, subtitle: str,
               tabs_html: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        "<title>Covenant Review Report</title>\n"
        f"<style>{CSS}</style>\n"
        "</head>\n<body>\n"
        '<header class="topbar">'
        '<div class="topbar-row">'
        f"<h1>Covenant Review · {h(doc_name)}</h1>"
        f'<div class="meta"><span>{h(subtitle)}</span></div>'
        "</div>"
        f'<div class="tabs" role="tablist">{tabs_html}</div>'
        "</header>\n"
        f'<main class="container">{body_html}</main>\n'
        f"<script>{JS}</script>\n"
        "</body>\n</html>\n"
    )


__all__ = ["render_report"]
