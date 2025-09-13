#!/usr/bin/env python3
"""
Generate styled Weekly Gazette DOCX/PDF files for one or many leagues.

- Reads leagues from --leagues (default: leagues.json)
- Pulls matchup data via gazette_data.fetch_week_from_espn
- Builds context via gazette_data.build_context
- Adds per-slot (MATCHUPi_*) keys and image placeholders for team logos
- Renders with docxtpl and (optionally) converts to PDF via LibreOffice

Usage:
  python3 generate_gazettes.py --slots 10 --pdf
  python3 generate_gazettes.py --league "My League" --week 1 --slots 8
  python3 generate_gazettes.py --print-logo-map
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

# Local modules in this repo
# - gazette_data: expected to provide build_context(...) and fetch_week_from_espn(...)
# - mascots_util: expected to provide logo_for(team_name: str) -> Optional[str]
try:
    from gazette_data import build_context, fetch_week_from_espn
except Exception as e:
    print("[error] Unable to import gazette_data. Make sure you're running from the repo root.", file=sys.stderr)
    raise

try:
    from mascots_util import logo_for as lookup_logo
except Exception:
    # Fallback shim if mascots_util isn't available for some reason
    def lookup_logo(_: str) -> Optional[str]:
        return None


# ---------- PDF helpers (LibreOffice, no Word needed) ----------
import subprocess


def to_pdf_with_soffice(docx_path: str) -> str:
    """Convert DOCX to PDF using LibreOffice. Returns the PDF path."""
    outdir = os.path.dirname(docx_path) or "."
    pdf_path = os.path.splitext(docx_path)[0] + ".pdf"
    cmd = ["soffice", "--headless", "--convert-to", "pdf", "--outdir", outdir, docx_path]
    try:
        subprocess.run(cmd, check=True)
    except Exception:
        # Homebrew sometimes doesn't symlink; use the app path directly
        cmd[0] = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
        subprocess.run(cmd, check=True)
    return pdf_path


def to_pdf(docx_path: str) -> str:
    """
    Try docx2pdf (Word) first if installed; fall back to LibreOffice.
    """
    try:
        from docx2pdf import convert as _convert  # type: ignore
        try:
            pdf_path = os.path.splitext(docx_path)[0] + ".pdf"
            _convert(docx_path, pdf_path)
            return pdf_path
        except Exception:
            return to_pdf_with_soffice(docx_path)
    except Exception:
        return to_pdf_with_soffice(docx_path)


# ---------- Logo discovery helpers ----------
LOGO_DIRS = [
    "logos/ai",
    "logos/generated_logos",
    "logos/generated_logo",   # singular (you mentioned this case)
    "logos",
]


def _sanitize_name(name: str) -> str:
    # Normalize to a filesystem-friendly base (e.g., "Nana's Hawks" -> "Nana_s_Hawks")
    base = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    base = re.sub(r"_+", "_", base)
    return base


def find_logo_path(team: str) -> Optional[str]:
    """
    Consolidated logo lookup:
      1) mascots_util.logo_for(team)
      2) search known logo directories for a sensible filename
    Returns absolute path if found, else None.
    """
    # 1) try mascots_util mapping
    try:
        p = lookup_logo(team)
        if p and Path(p).is_file():
            return str(Path(p).resolve())
    except Exception:
        pass

    # 2) scan directories
    candidates: List[Path] = []
    sanitized = _sanitize_name(team).lower()
    exts = [".png", ".jpg", ".jpeg", ".webp", ".bmp"]

    for d in LOGO_DIRS:
        base = Path(d)
        if not base.exists():
            continue

        # Try exact sanitized filename
        for ext in exts:
            cand = base / f"{sanitized}{ext}"
            if cand.is_file():
                return str(cand.resolve())

        # Try loose contains match (case-insensitive)
        try:
            for f in base.glob("*"):
                if f.is_file() and f.suffix.lower() in exts:
                    if sanitized in f.stem.lower():
                        candidates.append(f.resolve())
        except Exception:
            pass

    if candidates:
        # Choose shortest name as "best" match
        best = sorted(candidates, key=lambda p: len(p.name))[0]
        return str(best)

    return None


def add_logo_images(context: Dict[str, Any], doc: DocxTemplate, max_slots: int, width_mm: int = 25,
                    logo_map: Optional[Dict[str, str]] = None) -> None:
    """
    For each matchup i, add MATCHUPi_HOME_LOGO / MATCHUPi_AWAY_LOGO InlineImages into the context.
    If no image is found, set a visible fallback string "[no-logo]" so it's obvious in the doc.
    Optionally collect a {team: path} logo_map for printing.
    """
    for i in range(1, max_slots + 1):
        home = context.get(f"MATCHUP{i}_HOME", "") or ""
        away = context.get(f"MATCHUP{i}_AWAY", "") or ""

        # Home logo
        hp = find_logo_path(home) if home else None
        if hp and Path(hp).is_file():
            context[f"MATCHUP{i}_HOME_LOGO"] = InlineImage(doc, hp, width=Mm(width_mm))
            if logo_map is not None:
                logo_map[home] = hp
        else:
            context[f"MATCHUP{i}_HOME_LOGO"] = "[no-logo]"

        # Away logo
        ap = find_logo_path(away) if away else None
        if ap and Path(ap).is_file():
            context[f"MATCHUP{i}_AWAY_LOGO"] = InlineImage(doc, ap, width=Mm(width_mm))
            if logo_map is not None:
                logo_map[away] = ap
        else:
            context[f"MATCHUP{i}_AWAY_LOGO"] = "[no-logo]"


# ---------- Context mapping helpers ----------
def add_enumerated_matchups(context: Dict[str, Any], max_slots: int) -> None:
    """
    Expand context['games'] list into numbered keys the template uses:
    MATCHUPi_HOME, _AWAY, _HS, _AS, _BLURB, spotlight stats, plus legacy TEAMS/HEADLINE/BODY.
    """
    games: List[Dict[str, Any]] = context.get("games", []) or []
    for i in range(1, max_slots + 1):
        g = games[i - 1] if i - 1 < len(games) else {}

        home = g.get("home", "") or ""
        away = g.get("away", "") or ""
        hs = g.get("hs", "")
        aS = g.get("as", "")  # 'as' is a keyword; we keep the dict key but store as aS var

        blurb = g.get("blurb", "") or ""
        top_home = g.get("top_home", "") or ""
        top_away = g.get("top_away", "") or ""
        bust = g.get("bust", "") or ""
        keyplay = g.get("keyplay", "") or ""
        dnote = g.get("def", "") or ""

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

        # Legacy/compatibility fields
        try:
            hs_f = float(hs) if hs != "" else float("nan")
            as_f = float(aS) if aS != "" else float("nan")
            if hs != "" and aS != "":
                scoreline = f"{home} {hs} – {away} {aS}"
            else:
                scoreline = f"{home} vs {away}".strip()
            headline = f"{home if hs_f >= as_f else away} def. {away if hs_f >= as_f else home}"
        except Exception:
            scoreline = f"{home} vs {away}".strip()
            headline = scoreline

        context[f"MATCHUP{i}_TEAMS"] = scoreline
        context[f"MATCHUP{i}_HEADLINE"] = headline
        context[f"MATCHUP{i}_BODY"] = blurb


def add_template_synonyms(context: Dict[str, Any], slots: int) -> None:
    """
    Flatten award structures and add top-level aliases your Word template uses.
    """
    context["WEEK_NUMBER"] = context.get("week", "")
    if "WEEKLY_INTRO" not in context:
        context["WEEKLY_INTRO"] = context.get("intro", "")

    awards = context.get("awards", {}) or {}
    top_score = awards.get("top_score", {}) or {}
    low_score = awards.get("low_score", {}) or {}
    largest_gap = awards.get("largest_gap", {}) or {}

    context["AWARD_TOP_TEAM"] = top_score.get("team", "")
    context["AWARD_TOP_NOTE"] = str(top_score.get("points", "")) or ""
    context["AWARD_CUPCAKE_TEAM"] = low_score.get("team", "")
    context["AWARD_CUPCAKE_NOTE"] = str(low_score.get("points", "")) or ""
    context["AWARD_KITTY_TEAM"] = largest_gap.get("desc", "")
    context["AWARD_KITTY_NOTE"] = str(largest_gap.get("gap", "")) or ""


# ---------- Rendering ----------
def safe_title(s: str) -> str:
    s = re.sub(r"[^\w\s\-\(\)\._]", "_", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s


def render_single_league(cfg: Dict[str, Any], args: argparse.Namespace) -> Tuple[str, Optional[str], Dict[str, str]]:
    """
    Render one league's gazette. Returns (docx_path, pdf_path_or_None, logo_map).
    """
    league_id = cfg.get("league_id")
    year = cfg.get("year")
    espn_s2 = cfg.get("espn_s2", "")
    swid = cfg.get("swid", "")

    games = fetch_week_from_espn(league_id, year, espn_s2, swid)
    ctx = build_context(cfg, games)

    # Override via CLI if provided
    if args.week is not None:
        ctx["week_num"] = args.week  # optional, for your template if used
    if args.week_label:
        ctx["week"] = args.week_label
    if args.date:
        ctx["date"] = args.date

    # Per-matchup keys + images + synonyms
    add_enumerated_matchups(ctx, max_slots=args.slots)

    doc = DocxTemplate(args.template)

    logo_map: Dict[str, str] = {}
    add_logo_images(ctx, doc, max_slots=args.slots, width_mm=args.logo_mm, logo_map=logo_map)
    add_template_synonyms(ctx, slots=args.slots)

    # Missing placeholders check (useful when editing the template)
    #missing = doc.#get_undeclared_template_variables(ctx)
    #if missing:
     #   print(f"[warn] Template references unknown variables: {sorted(missing)}")

    # Output paths
    league_name = cfg.get("name", f"league_{league_id}") or f"league_{league_id}"
    out_dir = Path(args.out_dir) / safe_title(league_name)
    out_dir.mkdir(parents=True, exist_ok=True)

    week_label = ctx.get("week", f"Week_{ctx.get('week_num','')}")
    date_label = ctx.get("date", "")
    base = safe_title(f"Gazette_{week_label}_{date_label}") if date_label else safe_title(f"Gazette_{week_label}")

    docx_path = out_dir / f"{base}.docx"
    print("Context Keys;", list(ctx.keys()))
    doc.render(ctx)
    doc.save(str(docx_path))

    pdf_path: Optional[str] = None
    if args.pdf:
        pdf_path = to_pdf(str(docx_path))

    # Optional: print the used logo map so you can verify paths
    if args.print_logo_map:
        print(f"[logo-map] {league_name}:")
        for team, path in sorted(logo_map.items()):
            print(f"  - {team} -> {path}")

    return str(docx_path), pdf_path, logo_map


# ---------- CLI ----------
def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
		ap.add_argument("--llm-blurbs", action=argparse.BooleanOptionalAction, default=False,
                help="Enable/disable LLM blurbs"), help="Generate blurbs with the LLM")
    ap.add_argument("--blurb-words", type=int, default=500, help="Target word count per blurb")
    ap.add_argument("--temperature", type=float, default=0.7, help="LLM creativity setting")
    ap.add_argument("--blurb-style", type=str, default="neutral", help="Blurb style (e.g. mascot)")

    ap.add_argument("--leagues", default="leagues.json", help="Path to leagues config JSON.")
    ap.add_argument("--template", default="recap_template.docx", help="DOCX template to render.")
    ap.add_argument("--out-dir", default="recaps", help="Output root directory.")
    ap.add_argument("--pdf", action="store_true", help="Also export PDF (via LibreOffice/docx2pdf).")
    ap.add_argument("--league", default=None, help="Only render the league with this name.")
    ap.add_argument("--week", type=int, default=None, help="Force a specific completed week number.")
    ap.add_argument("--week-label", default=None, help='Override week label text, e.g. "Week 1 (Sep 4–9, 2025)".')
    ap.add_argument("--date", default=None, help="Override date label text.")
    ap.add_argument("--slots", type=int, default=10, help="Max matchup slots to render.")
    ap.add_argument("--logo-mm", type=int, default=25, help="Logo width in millimeters.")
    ap.add_argument("--print-logo-map", action="store_true", help="Print which logo file each team used.")
    return ap.parse_args()


def main() -> None:
    args = parse_args()

    # Load leagues list
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
