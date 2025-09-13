#!/usr/bin/env python3
"""
gg.py — Minimal, reliable DOCX renderer for Gridiron Gazette.

What it does:
- Loads a .dotx or .docx template
- Renders header/footer logo tags using InlineImage:
    {{ league_logo_tag }}  (header)
    {{ sponsor_logo_tag }} (footer)
- Writes a single output .docx

Zero tabs. Spaces only.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from shutil import copyfile
from typing import Any, Dict

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm


def resolve_template(path_str: str) -> Path:
    """Ensure template exists. If it's .dotx, copy to a .docx neighbor and return that path."""
    p = Path(path_str)
    if not p.exists():
        raise FileNotFoundError(f"Template not found: {p.resolve()}")

    if p.suffix.lower() == ".dotx":
        docx_copy = p.with_suffix(".docx")
        if not docx_copy.exists() or p.stat().st_mtime > docx_copy.stat().st_mtime:
            copyfile(p, docx_copy)
        return docx_copy

    return p


def build_context(tpl: DocxTemplate, args: argparse.Namespace) -> Dict[str, Any]:
    """Build docxtpl context including header/footer images + optional text fields."""
    ctx: Dict[str, Any] = {}

    if args.league_logo:
        league_path = Path(args.league_logo)
        if not league_path.exists():
            raise FileNotFoundError(f"League logo not found: {league_path.resolve()}")
        ctx["league_logo_tag"] = InlineImage(tpl, str(league_path), width=Mm(args.logo_mm))

    if args.sponsor_logo:
        sponsor_path = Path(args.sponsor_logo)
        if not sponsor_path.exists():
            raise FileNotFoundError(f"Sponsor logo not found: {sponsor_path.resolve()}")
        ctx["sponsor_logo_tag"] = InlineImage(tpl, str(sponsor_path), width=Mm(args.logo_mm))

    # Optional fields you might reference in the body
    if args.week is not None:
        ctx["week"] = args.week
    if args.slots is not None:
        ctx["slots"] = args.slots

    return ctx


def render_docx(template_path: Path, out_docx: Path, ctx: Dict[str, Any]) -> Path:
    """Render the template and save the final .docx."""
    out_docx.parent.mkdir(parents=True, exist_ok=True)
    tpl = DocxTemplate(str(template_path))
    tpl.render(ctx)
    tpl.save(str(out_docx))
    return out_docx


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Render a single Gridiron Gazette DOCX from a template.")
    p.add_argument("--template", required=True, help="Path to .dotx/.docx template.")
    p.add_argument("--out-docx", required=True, help="Output .docx path to write.")
    p.add_argument("--league-logo", help="Path to league logo image (png/jpg).")
    p.add_argument("--sponsor-logo", help="Path to sponsor/business logo image (png/jpg).")
    p.add_argument("--logo-mm", type=float, default=28.0, help="Logo width in millimeters (default: 28).")
    p.add_argument("--week", type=int, help="Week number (optional).")
    p.add_argument("--slots", type=int, help="Slot count (optional).")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # Resolve template (and copy .dotx -> .docx for docxtpl friendliness)
    template_path = resolve_template(args.template)

    # Build context and render
    ctx = build_context(DocxTemplate(str(template_path)), args)
    # Recreate tpl after context sizing (ensures relationships clean)
    tpl = DocxTemplate(str(template_path))
    tpl.render(ctx)

    out_path = Path(args.out_docx)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tpl.save(str(out_path))
    print(f"[ok] Wrote DOCX: {out_path.resolve()}")


if __name__ == "__main__":
    main()