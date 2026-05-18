# aplma

Covenant extraction and review tool for APLMA-style facility agreements.

Given a facility agreement PDF, `aplma` locates, extracts, and structures the key covenant clauses — starting with Financial Indebtedness — and produces a self-contained HTML review report.

## How it works

The pipeline runs five steps per covenant spec:

1. **Ingest** — Docling converts the PDF into a structured document
2. **Vision TOC** — Gemini reads the table-of-contents pages as images to get accurate physical page numbers
3. **Scout** — Gemini identifies which page ranges contain the target covenant (definition + restriction sections)
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

Open `colab_notebook.ipynb` in Colab. Add your Gemini API key to Colab Secrets as `GEMINI_API_KEY`, then run all cells.

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

Edit `financial_indebtedness.yaml` to tune extraction for agreements that use non-standard wording, or add a new `.yaml` file for a different covenant type.

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
