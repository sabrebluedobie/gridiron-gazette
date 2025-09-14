#!/usr/bin/env python3
"""
gg.py — Minimal, reliable DOCX renderer for Gridiron Gazette.

- Accepts .docx or .dotx template paths.
- If .dotx is provided, it copies to a sibling .docx and renders from that.
- Embeds header/footer logos using docxtpl InlineImage with tags:
    Header: {{ league_logo_tag }}
    Footer: {{ sponsor_logo_tag }}
- Writes a single output .docx

Indentation: spaces only (no tabs).
"""

from __future__ import annotations

import argparse
from pathlib import Path
from shutil import copyfile
from typing import Any, Dict

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm


def resolve_template(path_str: str) -> Path:
    """
    Ensure the template exists. If the input is .dotx, copy to .docx and return the .docx path.
    If it's already .docx, return it as-is.
    """
    p = Path(path_str)
    if not p.exists():
        # Show absolute path for clearer error messages
        raise FileNotFoundError(f"Template not found: {p.resolve()}")

    if p.suffix.lower() == ".dotx":
        docx_copy = p.with_suffix(".docx")
        # Only (re)copy when needed
        if (not docx_copy.exists()) or (p.stat().st_mtime > docx_copy.stat().st_mtime):
            copyfile(p, docx_copy)
        return docx_copy

    # Use .docx directly
    return p


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Render a single Gridiron Gazette DOCX from a template.")
    p.add_argument("--template", required=True, help="Path to .docx or .dotx template.")
    p.add_argument("--out-docx", required=True, help="Output .docx path to write.")
    p.add_argument("--league-logo", help="Path to league logo image (png/jpg).")
    p.add_argument("--sponsor-logo", help="Path to sponsor/business logo image (png/jpg).")
    p.add_argument("--logo-mm", type=float, default=28.0, help="Logo width in millimeters (default: 28).")
    p.add_argument("--week", type=int, help="Week number (optional).")
    p.add_argument("--slots", type=int, help="Slot count (optional).")
    return p.parse_args()


def build_context(tpl: DocxTemplate, args: argparse.Namespace) -> Dict[str, Any]:
    """
    Build the docxtpl context. Header/footer logos are optional; include them only if provided.
    """
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

    # Optional text fields you may show in the body
    if use_week is not None:
        ctx["week"] = use_week
    if args.slots is not None:
        ctx["slots"] = args.slots

    return ctx


def main() -> None:
    args = parse_args()

    # Resolve template path first (handles .dotx → .docx copy)
    template_path = resolve_template(args.template)

    # Build context and render
    tpl = DocxTemplate(str(template_path))
    ctx = build_context(tpl, args)
    tpl.render(ctx)

    out_path = Path(args.out_docx)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tpl.save(str(out_path))
    print(f"[ok] Wrote DOCX: {out_path.resolve()}")


if __name__ == "__main__":
    main()