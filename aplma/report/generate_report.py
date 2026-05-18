"""CLI entry point for the covenant review report.

Usage:
    python -m aplma.report.generate_report --pdf agreement.pdf --out review_report.html

Defaults to running the bundled financial_indebtedness spec when no --spec is given.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import aplma.config as config
from aplma.specs.loader import DEFAULT_SPEC_PATH

from aplma.report.html_report import render_report
from aplma.report.review_session import build_sessions


_SPEC_ALIASES: dict[str, Path] = {
    "financial_indebtedness": DEFAULT_SPEC_PATH,
}

_DEFAULT_SPECS = ["financial_indebtedness"]


def _resolve_spec(name: str) -> Path:
    if name in _SPEC_ALIASES:
        return _SPEC_ALIASES[name]
    path = Path(name)
    if path.exists():
        return path
    raise ValueError(
        f"Unknown spec: {name!r}. "
        f"Known aliases: {sorted(_SPEC_ALIASES)}. "
        "Or pass a path to a .yaml file."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the multi-covenant review report.")
    parser.add_argument("--pdf", required=True, help="Path to the PDF to analyse.")
    parser.add_argument(
        "--out",
        default="review_report.html",
        help="Output HTML path (default: review_report.html).",
    )
    parser.add_argument(
        "--spec",
        action="append",
        default=None,
        help=(
            "Spec name or YAML path. Repeat to add more. "
            f"Default: {' '.join(_DEFAULT_SPECS)}."
        ),
    )
    args = parser.parse_args()

    if not config.GEMINI_API_KEY:
        raise EnvironmentError(
            "GEMINI_API_KEY not set. Export it in your environment "
            "or add it to .env."
        )

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    spec_names = args.spec if args.spec else list(_DEFAULT_SPECS)
    spec_paths = [_resolve_spec(name) for name in spec_names]

    print(f"Generating review report for {pdf_path.name}")
    print(f"Specs: {', '.join(spec_names)}")

    sessions = build_sessions(pdf_path, spec_paths)
    for s in sessions:
        status = "OK" if s.failed_stage is None else f"FAILED ({s.failed_stage})"
        print(f"  - {s.spec.covenant_type}: {status}")

    html_text = render_report(sessions)
    out_path = Path(args.out)
    out_path.write_text(html_text, encoding="utf-8")
    print(f"\nReport → {out_path.resolve()}")


if __name__ == "__main__":
    main()
