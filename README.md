# aplma

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/gabrielchan1010/aplma/blob/main/colab_notebook.ipynb)

Covenant extraction and review tool for APLMA-style facility agreements.

Given a facility agreement PDF, `aplma` locates and extracts target covenant clauses together with the defined terms they rely on — starting with the **restriction on Financial Indebtedness** (and its underlying *Financial Indebtedness* / *Permitted Financial Indebtedness* defined terms) — and produces a self-contained HTML review report.

> **Status:** early prototype. Scoped to one negative covenant (the restriction on Financial Indebtedness) to validate the end-to-end workflow with a subject-matter expert. The pipeline is built to extend to other covenants — Disposals, Negative Pledge, Information Undertakings, and so on — once the workflow holds up against real agreements.

## How it works

The pipeline runs five steps per covenant spec:

1. **Ingest** — Docling converts the PDF into a structured document
2. **Vision TOC** — Gemini reads the table-of-contents pages as images to get accurate physical page numbers
3. **Scout** — Gemini identifies which page ranges contain the target restriction clause and the defined terms it relies on
4. **Slicer** — fetches the raw text from those page ranges
5. **Structural parser** — a deterministic, LLM-free pass that extracts the definition text, restriction clause, and permitted carve-outs with grounded page references

## Setup

**Prerequisites:** Python 3.10+, a [Gemini API key](https://aistudio.google.com/app/apikey)

```bash
# Install
pip install -e ".[dev]"

# Configure secrets
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=your-key-here
```

## Usage

### Command line

```bash
python -m aplma.report.generate_report --pdf agreement.pdf --out review_report.html
```

### Google Colab

Click the **Open in Colab** badge above (or open `colab_notebook.ipynb` directly in Colab). Add your Gemini API key to Colab Secrets as `GEMINI_API_KEY`, toggle *Notebook access* on, then run all cells.

For a step-by-step walkthrough aimed at non-technical users, see the [onboarding deck](https://gabrielchan1010.github.io/aplma/onboarding.html) (or open `onboarding.html` locally).

### Python API

```python
from aplma.report.review_session import build_sessions
from aplma.report.html_report import render_report
from aplma.specs.loader import DEFAULT_SPEC_PATH
from pathlib import Path

sessions = build_sessions(Path("agreement.pdf"), [DEFAULT_SPEC_PATH])
html = render_report(sessions)
Path("review_report.html").write_text(html)
```

## Covenant specs

Specs live in `aplma/specs/` as YAML files. Each spec tells the pipeline:
- What search terms to use when locating pages (used by the Scout LLM)
- What literal phrases mark the start of each definition (used by the structural parser)
- What heading suffix identifies the restriction clause

Edit `financial_indebtedness.yaml` to tune extraction for agreements that use non-standard wording. Adding a **new** covenant type requires two things:

1. A new YAML spec in `aplma/specs/` describing the search terms and structural anchors
2. A structural parser registered in [aplma/pipeline/structural_parser.py](aplma/pipeline/structural_parser.py) and a Pydantic model in [aplma/models/](aplma/models/) for the covenant's data shape

Today only the `financial_indebtedness` parser is registered.

## Environment variables

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Required. Google Gemini API key. |

## Dependencies

| Package | Purpose |
|---|---|
| `docling` | PDF parsing and document structure extraction |
| `google-genai` | Gemini API (vision TOC + LLM scout) |
| `pydantic` | Structured output models |
| `pyyaml` | Covenant spec loading |
