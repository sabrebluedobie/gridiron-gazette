#!/usr/bin/env python3
"""
Generate styled Weekly Gazette DOCX/PDF files for one or many leagues.

Usage examples:
  python3 gazette_runner.py --slots 10
  python3 gazette_runner.py --slots 10 --pdf
  python3 gazette_runner.py --league "My League" --week 1 --slots 8
  python3 gazette_runner.py --print-logo-map
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Third-party
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

# Local deps
try:
    from gazette_data import build_context, fetch_week_from_espn
except Exception as e:
    print("[error] Unable to import gazette_data. Run from repo root and ensure your venv is active.", file=sys.stderr)
    raise

try:
    from mascots_util import logo_for as lookup_logo  # optional mapping file
except Exception:
    def lookup_logo(_: str) -> Optional[str]:
        return None

# ---------------- PDF helpers ----------------

import subprocess

def to_pdf_with_soffice(docx_path: str) -> str:
    """Convert DOCX to PDF using LibreOffice. Returns the PDF path."""
    outdir = os.path.dirname(docx_path) or "."
    pdf_path = os.path.splitext(docx_path)[0] + ".pdf"
    cmd = ["soffice", "--headless", "--convert-to", "pdf", "--outdir", outdir, docx_path]
    try:
        subprocess.run(cmd, check=True)
    except Exception:
        # Homebrew sometimes doesn't symlink 'soffice'
        cmd[0] = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
        subprocess.run(cmd, check=True)
    return pdf_path

def to_pdf(docx_path: str) -> str:
    """Try Word (docx2pdf) first; fallback to LibreOffice."""
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

# --------------- Logo helpers ----------------

LOGO_DIRS = [
    "logos/ai",
    "logos/generated_logos",
    "logos/generated_logo",  # singular (you mentioned this case)
    "logos",
]

def _sanitize_name(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    return re.sub(r"_+", "_", base)

def find_logo_path(team: str) -> Optional[str]:
    """1) mascots_util mapping, then 2) scan known dirs for likely filename."""
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

        # exact sanitized
        for ext in exts:
            cand = base / f"{sanitized}{ext}"
            if cand.is_file():
                return str(cand.resolve())

        # loose contains
        for f in base.glob("*"):
            if f.is_file() and f.suffix.lower() in exts:
                if sanitized in f.stem.lower():
                    candidates.append(f.resolve())

    if candidates:
        return str(sorted(candidates, key=lambda p: len(p.name))[0])
    return None

def add_logo_images(context: Dict[str, Any], doc: DocxTemplate, max_slots: int,
                    width_mm: int = 25, logo_map: Optional[Dict[str, str]] = None) -> None:
    """Inject InlineImage objects for each matchup's home/away team."""
    for i in range(1, max_slots + 1):
        home = context.get(f"MATCHUP{i}_HOME", "") or ""
        away = context.get(f"MATCHUP{i}_AWAY", "") or ""

        hp = find_logo_path(home) if home else None
        ap = find_logo_path(away) if away else None

        context[f"MATCHUP{i}_HOME_LOGO"] = (
            InlineImage(doc, hp, width=Mm(width_mm)) if hp and Path(hp).is_file() else "[no-logo]"
        )
        context[f"MATCHUP{i}_AWAY_LOGO"] = (
            InlineImage(doc, ap, width=Mm(width_mm)) if ap and Path(ap).is_file() else "[no-logo]"
        )

        if logo_map is not None:
            if hp: logo_map[home] = hp
            if ap: logo_map[away] = ap

# ------------- Context expansion -------------

def add_enumerated_matchups(context: Dict[str, Any], max_slots: int) -> None:
    """Explode context['games'] -> MATCHUPi_* keys used by the Word template."""
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

        context[f"MATCHUP{i}_HOME"]      = home
        context[f"MATCHUP{i}_AWAY"]      = away
        context[f"MATCHUP{i}_HS"]        = hs
        context[f"MATCHUP{i}_AS"]        = aS
        context[f"MATCHUP{i}_BLURB"]     = blurb
        context[f"MATCHUP{i}_TOP_HOME"]  = top_home
        context[f"MATCHUP{i}_TOP_AWAY"]  = top_away
        context[f"MATCHUP{i}_BUST"]      = bust
        context[f"MATCHUP{i}_KEYPLAY"]   = keyplay
        context[f"MATCHUP{i}_DEF"]       = dnote

        # Legacy/compatibility fields
        try:
            hs_f = float(hs) if hs != "" else float("nan")
            as_f = float(aS) if aS != "" else float("nan")
            if hs != "" and aS != "":
                scoreline = f"{home} {hs} – {away} {aS}"
            else:
                scoreline = f"{home} vs {away}".strip()
            winner = home if hs_f >= as_f else away
            loser  = away if hs_f >= as_f else home
            headline = f"{winner} def. {loser}" if home and away else scoreline
        except Exception:
            scoreline = f"{home} vs {away}".strip()
            headline = scoreline

        context[f"MATCHUP{i}_TEAMS"]    = scoreline
        context[f"MATCHUP{i}_HEADLINE"] = headline
        context[f"MATCHUP{i}_BODY"]     = blurb

def add_template_synonyms(context: Dict[str, Any], slots: int) -> None:
    """Flatten award structures and add a few top-level aliases."""
    context["WEEK_NUMBER"] = context.get("week", "")
    if "WEEKLY_INTRO" not in context:
        context["WEEKLY_INTRO"] = context.get("intro", "")

    awards = context.get("awards", {}) or {}
    top_score   = awards.get("top_score", {}) or {}
    low_score   = awards.get("low_score", {}) or {}
    largest_gap = awards.get("largest_gap", {}) or {}

    context["AWARD_TOP_TEAM"]      = top_score.get("team", "")
    context["AWARD_TOP_NOTE"]      = str(top_score.get("points", "")) or ""
    context["AWARD_CUPCAKE_TEAM"]  = low_score.get("team", "")
    context["AWARD_CUPCAKE_NOTE"]  = str(low_score.get("points", "")) or ""
    context["AWARD_KITTY_TEAM"]    = largest_gap.get("desc", "")
    context["AWARD_KITTY_NOTE"]    = str(largest_gap.get("gap", "")) or ""

# ---------------- Rendering ------------------

def safe_title(s: str) -> str:
    s = re.sub(r"[^\w\s\-\(\)\._]", "_", s)
    return re.sub(r"\s+", "_", s).strip("_")

def render_single_league(cfg: Dict[str, Any], args: argparse.Namespace) -> Tuple[str, Optional[str], Dict[str, str]]:
    """Return (docx_path, pdf_path_or_None, logo_map)."""
    league_id = cfg.get("league_id")
    year      = cfg.get("year")
    espn_s2   = cfg.get("espn_s2", "")
    swid      = cfg.get("swid", "")

    games = fetch_week_from_espn(league_id, year, espn_s2, swid)
    ctx = build_context(cfg, games)

    # Optional CLI overrides
    if args.week is not None:
        ctx["week_num"] = args.week
    if args.week_label:
        ctx["week"] = args.week_label
    if args.date:
        ctx["date"] = args.date

    add_enumerated_matchups(ctx, max_slots=args.slots)

    doc = DocxTemplate(args.template)
    logo_map: Dict[str, str] = {}
    add_logo_images(ctx, doc, max_slots=args.slots, width_mm=args.logo_mm, logo_map=logo_map)
    add_template_synonyms(ctx, slots=args.slots)

    # Helpful when editing templates; use named arg to avoid version quirks
    try:
        missing = doc.get_undeclared_template_variables(context=ctx)
        if missing:
            print(f"[warn] Template references unknown variables: {sorted(missing)}")
    except Exception as e:
        print(f"[warn] Could not compute undeclared variables ({e.__class__.__name__}: {e})")

    league_name = cfg.get("name", f"league_{league_id}") or f"league_{league_id}"
    out_dir = Path(args.out_dir) / safe_title(league_name)
    out_dir.mkdir(parents=True, exist_ok=True)

    week_label = ctx.get("week", f"Week_{ctx.get('week_num','')}")
    date_label = ctx.get("date", "")
    base = safe_title(f"Gazette_{week_label}_{date_label}") if date_label else safe_title(f"Gazette_{week_label}")

    docx_path = out_dir / f"{base}.docx"
    doc.render(ctx)
    doc.save(str(docx_path))

    pdf_path: Optional[str] = None
    if args.pdf:
        pdf_path = to_pdf(str(docx_path))

    if args.print_logo_map:
        print(f"[logo-map] {league_name}:")
        for team, path in sorted(logo_map.items()):
            print(f"  - {team} -> {path}")

    return str(docx_path), pdf_path, logo_map

# ----------------- CLI ----------------------

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", default="leagues.json", help="Path to leagues config JSON.")
    ap.add_argument("--template", default="recap_template.docx", help="DOCX template to render.")
    ap.add_argument("--out-dir", default="recaps", help="Output root directory.")
    ap.add_argument("--pdf", action="store_true", help="Also export PDF (via LibreOffice/docx2pdf).")
    ap.add_argument("--league", default=None, help="Only render the league with this name.")
    ap.add_argument("--week", type=int, default=None, help="Force a specific completed week number.")
    ap.add_argument("--week-label", default=None, help='Override week text, e.g. "Week 1 (Sep 4–9, 2025)".')
    ap.add_argument("--date", default=None, help="Override date label text.")
    ap.add_argument("--slots", type=int, default=10, help="Max matchup slots to render.")
    ap.add_argument("--logo-mm", type=int, default=25, help="Logo width in millimeters.")
    ap.add_argument("--print-logo-map", action="store_true", help="Print which logo file each team used.")
    return ap.parse_args()

def main() -> None:
    args = parse_args()

    leagues_path = Path(args.leagues)
    if not leagues_path.exists():
        print(f"[error] Leagues file not found: {leagues_path}", file=sys.stderr)
        sys.exit(1)

    try:
        leagues: List[Dict[str, Any]] = json.loads(leagues_path.read_text())
    except Exception as e:
        print(f"[error] Failed to read {leagues_path}: {e}", file=sys.stderr)
        sys.exit(1)

    # Optional filter by league name
    items = [l for l in leagues if not args.league or l.get("name") == args.league]
    if not items:
        print("[warn] No leagues matched the filter; nothing to do.")
        return

    for cfg in items:
        docx, pdf, _ = render_single_league(cfg, args)
        print(f"[ok] Wrote DOCX: {docx}")
        if pdf:
            print(f"[ok] Wrote PDF:  {pdf}")

if __name__ == "__main__":
    main()
