"""Project-wide configuration.

Secrets (API keys) are loaded from .env automatically in development.
Copy .env.example to .env and fill in your values. Never commit .env.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=False)
except ImportError:
    pass

# ── Paths ─────────────────────────────────────────────────────────────────────

DOCUMENTS_DIR: Path = Path.cwd() / "documents"
DEFAULT_PDF_PATH: Path = Path.cwd() / "agreement.pdf"

# ── Secrets ───────────────────────────────────────────────────────────────────

GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")

# ── Document structure ────────────────────────────────────────────────────────

TOC_PAGES: list[int] = [2, 3]

# ── Models ────────────────────────────────────────────────────────────────────

ROUTING_MODEL: str = "gemma-4-26b-a4b-it"
VISION_TOC_MODEL: str = "gemini-3.1-flash-lite-preview"

# Scout LLM-initiated tool-call budget (pre-fetch via spec search_terms is free).
SCOUT_MAX_TOOL_CALLS: int = 0
