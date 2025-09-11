#!/usr/bin/env python3
"""
Quick template debugger:
- Loads first league from leagues.json
- Pulls games via fetch_week_from_espn + build_context
- Expands MATCHUPi_* keys
- Injects logos (InlineImage) so you can spot issues
- Prints context keys and any undeclared template variables
- Renders to recaps/_debug/Debug_Gazette.docx (and optional --pdf)

Usage:
  python3 debug_template.py --template recap_template.docx --slots 10 --pdf
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

# Local deps
from gazette_data import build_context, fetch_week_from_espn

# ----- minimal helpers duplicated here to avoid circular imports -----

LOGO_DIRS = [
    "logos/ai",
    "logos/generated_logos",
    "logos/generated_logo",
    "logos",
]

def _sanitize_name(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    return re.sub(r"_+", "_", base)

def find_logo_path(team: str) -> Optional[str]:
    from mascots_util import logo_for as lookup_logo  # local mapping if present
    try:
        p = lookup_logo(team)
        if p and Path(p).is_file():
            return str(Path(p).resolve())
    except Exception:
        pass

    candidates: List[Path] = []
    sanitized = _sanitize_name(team).lower()
    exts = (".png", ".jpg", ".jpeg", ".webp", ".bmp")

    for d in LOGO_DIRS:
        base = Path(d)
        if not base.exists():
            continue
        for ext in exts:
            cand = base / f"{sanitized}{ext}"
            if cand.is_file():
                return str(cand.resolve())
        for f in base.glob("*"):
            if f.is_file() and f.suffix.lower() in exts and sanitized in f.stem.lower():
                candidates.append(f.resolve())
    if candidates:
        return str(sorted(candidates, key=lambda p: len(p.name))[0])
    return None

def add_logo_images(context: Dict[str, Any], doc: DocxTemplate, max_slots: int, width_mm: int = 25) -> None:
    for i in range(1, max_slots + 1):
        home = context.get(f"MATCHUP{i}_HOME", "") or ""
        away = context.get(f"MATCHUP{i}_AWAY", "") or ""
        hp = find_logo_path(home) if home else None
        ap = find_logo_path(away) if away else None
        context[f"MATCHUP{i}_HOME_LOGO"] = InlineImage(doc, hp, width=Mm(width_mm)) if hp else "[no-logo]"
        context[f"MATCHUP{i}_AWAY_LOGO"] = InlineImage(doc, ap, width=Mm(width_mm)) if ap else "[no-logo]"

def add_enumerated_matchups(context: Dict[str, Any], max_slots: int) -> None:
    games: List[Dict[str, Any]] = context.get("games", []) or []
    for i in range(1, max_slots + 1):
        g = games[i - 1] if i - 1 < len(games) else {}
        home = g.get("home", "") or ""
        away = g.get("away", "") or ""
        hs   = g.get("hs", "")
        aS   = g.get("as", "")
        blurb    = g.get("blurb", "") or ""
        top_home = g.get("top_home", "") or ""
        top_away = g.get("top_away", "") or ""
        bust     = g.get("bust", "") or ""
        keyplay  = g.get("keyplay", "") or ""
        dnote    = g.get("def", "") or ""
        context[f"MATCHUP{i}_HOME"] = home
        context[f"MATCHUP{i}_AWAY"] = away
        context[f"MATCHUP{i}_HS"] = hs
        context[f"MATCHUP{i}_AS"] = aS
        context[f"MATCHUP{i}_BLURB"] = blurb
        context[f"MATCHUP{i}_TOP_HOME"] = top_home
        context[f"MATCHUP{i}_TOP_AWAY"] = top_away
        context[f"MATCHUP{i}_BUST"] = bust
        context[f"MATCHUP{i}_KEYPLAY"] = keyplay
        context[f"MATCHUP{i}_DEF"] = dnote

def to_pdf_with_soffice(docx_path: str) -> str:
    import subprocess
    outdir = os.path.dirname(docx_path) or "."
    pdf_path = os.path.splitext(docx_path)[0] + ".pdf"
    cmd = ["soffice", "--headless", "--convert-to", "pdf", "--outdir", outdir, docx_path]
    try:
        subprocess.run(cmd, check=True)
    except Exception:
        cmd[0] = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
        subprocess.run(cmd, check=True)
    return pdf_path

def to_pdf(docx_path: str) -> str:
    try:
        from docx2pdf import convert as _convert  # type: ignore
        pdf_path = os.path.splitext(docx_path)[0] + ".pdf"
        try:
            _convert(docx_path, pdf_path)
            return pdf_path
        except Exception:
            return to_pdf_with_soffice(docx_path)
    except Exception:
        return to_pdf_with_soffice(docx_path)

def safe_title(s: str) -> str:
    s = re.sub(r"[^\w\s\-\(\)\._]", "_", s)
    return re.sub(r"\s+", "_", s).strip("_")

# -------------------- script --------------------

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", default="leagues.json")
    ap.add_argument("--template", default="recap_template.docx")
    ap.add_argument("--slots", type=int, default=10)
    ap.add_argument("--logo-mm", type=int, default=25)
    ap.add_argument("--out-dir", default="recaps/_debug")
    ap.add_argument("--pdf", action="store_true")
    return ap.parse_args()

def main() -> None:
    args = parse_args()

    tpl = DocxTemplate(args.template)

    leagues = json.loads(Path(args.leagues).read_text())
    cfg = leagues[0] if leagues else {}
    games = fetch_week_from_espn(cfg.get("league_id"), cfg.get("year"),
                                 cfg.get("espn_s2", ""), cfg.get("swid", ""))
    ctx = build_context(cfg, games)

    add_enumerated_matchups(ctx, max_slots=args.slots)
    add_logo_images(ctx, tpl, max_slots=args.slots, width_mm=args.logo_mm)

    # Helpful prints
    print("Context keys sample:", sorted(list(ctx.keys()))[:25], "…")
    try:
        missing = tpl.get_undeclared_template_variables(context=ctx)  # named arg to avoid version quirks
        if missing:
            print("[warn] Undeclared in template:", sorted(missing))
        else:
            print("[ok] Template variables all declared.")
    except Exception as e:
        print(f"[warn] Could not compute undeclared vars ({e.__class__.__name__}: {e})")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_docx = out_dir / f"{safe_title('Debug_Gazette')}.docx"

    tpl.render(ctx)
    tpl.save(str(out_docx))
    print(f"[ok] Wrote DOCX: {out_docx}")

    if args.pdf:
        pdf = to_pdf(str(out_docx))
        print(f"[ok] Wrote PDF:  {pdf}")

if __name__ == "__main__":
    main()
