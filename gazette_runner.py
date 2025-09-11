#!/usr/bin/env python3
"""
Generate styled Weekly Gazette DOCX/PDF files for one or many leagues.

Usage examples:
  # normal run (DOCX)
  python3 gazette_runner.py --slots 10

  # with PDF export
  python3 gazette_runner.py --slots 10 --pdf

  # force a specific week (recommended to sanity check)
  python3 gazette_runner.py --slots 10 --week 1 --pdf

  # only one league by name (must match leagues.json "name")
  python3 gazette_runner.py --league "BrownSEA-KC League" --slots 10 --pdf

  # branding smoke test (no ESPN calls)
  python3 gazette_runner.py --branding-test --slots 1 --print-logo-map

  # long-form blurbs via OpenAI (with fallback if API fails)
  export ***REMOVED***
  python3 gazette_runner.py --slots 10 --llm-blurbs --blurb-words 180 --temperature 0.6 --pdf
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

# Third-party
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

# Local modules
try:
    from gazette_data import build_context, fetch_week_from_espn
except Exception as e:
    print("[error] Unable to import gazette_data. Run from the repo root. ", e, file=sys.stderr)
    raise

# Optional: use mascots_util mapping if available
try:
    from mascots_util import logo_for as lookup_logo  # returns a path or None
except Exception:
    def lookup_logo(_: str) -> Optional[str]:
        return None


# -------------------- PDF helpers --------------------

def to_pdf_with_soffice(docx_path: str) -> str:
    """Convert DOCX to PDF using LibreOffice. Returns PDF path."""
    outdir = os.path.dirname(docx_path) or "."
    pdf_path = os.path.splitext(docx_path)[0] + ".pdf"
    cmd = ["soffice", "--headless", "--convert-to", "pdf", "--outdir", outdir, docx_path]
    try:
        subprocess.run(cmd, check=True)
    except Exception:
        # Homebrew sometimes doesn’t symlink; call the app directly
        cmd[0] = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
        subprocess.run(cmd, check=True)
    return pdf_path


def to_pdf(docx_path: str) -> str:
    """
    Try docx2pdf (Word) first if installed; otherwise fall back to LibreOffice.
    """
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


# -------------------- Logo discovery --------------------

LOGO_DIRS = [
    "logos/generated_logos",
    "logos/ai",
    "logos/generated_logo",   # singular, just in case
    "logos",
]

IMG_EXTS = [".png", ".jpg", ".jpeg", ".webp", ".bmp"]


def _sanitize_name(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    return re.sub(r"_+", "_", base)


def find_logo_path(team_or_path: str) -> Optional[str]:
    """
    If it's a valid file path, use it.
    Else try mascots_util mapping.
    Else scan known logo folders for a close match.
    Returns absolute path or None.
    """
    if not team_or_path:
        return None

    p = Path(team_or_path)
    if p.suffix.lower() in IMG_EXTS and p.exists():
        return str(p.resolve())

    # mascots_util mapping (can point anywhere)
    try:
        m = lookup_logo(team_or_path)
        if m and Path(m).is_file():
            return str(Path(m).resolve())
    except Exception:
        pass

    # directory scan by name
    key = _sanitize_name(team_or_path).lower()
    candidates: List[Path] = []
    for base in LOGO_DIRS:
        d = Path(base)
        if not d.exists():
            continue

        # exact filename first
        for ext in IMG_EXTS:
            cand = d / f"{key}{ext}"
            if cand.is_file():
                return str(cand.resolve())

        # loose contains match
        for f in d.glob("*"):
            if f.is_file() and f.suffix.lower() in IMG_EXTS:
                if key in f.stem.lower():
                    candidates.append(f.resolve())

    if candidates:
        # choose the shortest filename as best match
        best = sorted(candidates, key=lambda x: len(x.name))[0]
        return str(best)

    return None


# -------------------- ESPN adapter --------------------

def adapt_games_for_build_context(games_list: List[Any]) -> List[Any]:
    """
    Normalize dicts/objects so build_context can safely use attribute access like:
    g.home, g.away, g.hs, g.ascore, g.home_top, g.away_top,
    g.biggest_bust, g.key_play, g.defense_note, g.blurb.
    """
    def num(x):
        try:
            return float(x)
        except Exception:
            return x

    EXPECTED = [
        "home", "away", "hs", "ascore",
        "home_top", "away_top",
        "biggest_bust", "key_play", "defense_note",
        "blurb",
    ]

    out: List[Any] = []
    for g in (games_list or []):
        if isinstance(g, dict):
            home = g.get("home") or g.get("home_team") or ""
            away = g.get("away") or g.get("away_team") or ""
            hs   = num(g.get("hs", g.get("home_score", g.get("hscore", g.get("score_home", "")))))
            a    = num(g.get("as", g.get("away_score", g.get("ascore", g.get("score_away", "")))))

            top_home     = g.get("home_top", g.get("top_home", ""))
            top_away     = g.get("away_top", g.get("top_away", ""))
            biggest_bust = g.get("biggest_bust", g.get("bust", g.get("bust_player", "")))
            key_play     = g.get("key_play", g.get("keyplay", ""))
            defense_note = g.get("defense_note", g.get("defense", g.get("dnote", g.get("def", ""))))
            blurb        = g.get("blurb", "")

            ns = SimpleNamespace(
                # canonical
                home=home, away=away, hs=hs, ascore=a,
                # score aliases
                hscore=hs, home_score=hs, score_home=hs,
                away_score=a, score_away=a,
                # spotlight/notes (canonical + alternates)
                home_top=top_home, away_top=top_away,
                top_home=top_home, top_away=top_away,
                biggest_bust=biggest_bust, bust=biggest_bust, bust_player=biggest_bust,
                key_play=key_play, keyplay=key_play,
                defense_note=defense_note, defense=defense_note, dnote=defense_note,
                blurb=blurb,
            )
        else:
            # already an object (e.g., from espn_api)
            ns = g
            if not hasattr(ns, "ascore") and hasattr(ns, "away_score"): setattr(ns, "ascore", getattr(ns, "away_score"))
            if not hasattr(ns, "hs")     and hasattr(ns, "home_score"): setattr(ns, "hs",     getattr(ns, "home_score"))
            if not hasattr(ns, "home_top") and hasattr(ns, "top_home"): setattr(ns, "home_top", getattr(ns, "top_home"))
            if not hasattr(ns, "away_top") and hasattr(ns, "top_away"): setattr(ns, "away_top", getattr(ns, "top_away"))
            if not hasattr(ns, "biggest_bust") and hasattr(ns, "bust"): setattr(ns, "biggest_bust", getattr(ns, "bust"))
            if not hasattr(ns, "key_play") and hasattr(ns, "keyplay"):   setattr(ns, "key_play", getattr(ns, "keyplay"))
            if not hasattr(ns, "defense_note") and hasattr(ns, "defense"):
                setattr(ns, "defense_note", getattr(ns, "defense"))

        # final safety net: guarantee fields exist
        for name in EXPECTED:
            if not hasattr(ns, name):
                setattr(ns, name, "")

        out.append(ns)
    return out


# -------------------- Template/context helpers --------------------

def safe_title(s: str) -> str:
    s = re.sub(r"[^\w\s\-\(\)\._]", "_", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s


def add_enumerated_matchups(context: Dict[str, Any], max_slots: int) -> None:
    """
    Expand context['games'] into MATCHUPi_* keys for the template.
    """
    games: List[Dict[str, Any]] = context.get("games", []) or []
    for i in range(1, max_slots + 1):
        g = games[i - 1] if i - 1 < len(games) else {}

        home = g.get("home", "") or ""
        away = g.get("away", "") or ""
        hs   = g.get("hs", "")
        aS   = g.get("as", g.get("ascore", ""))

        blurb    = g.get("blurb", "") or ""
        top_home = g.get("top_home", g.get("home_top", "")) or ""
        top_away = g.get("top_away", g.get("away_top", "")) or ""
        bust     = g.get("biggest_bust", g.get("bust", "")) or ""
        keyplay  = g.get("key_play", g.get("keyplay", "")) or ""
        dnote    = g.get("defense_note", g.get("def", "")) or ""

        context[f"MATCHUP{i}_HOME"] = home
        context[f"MATCHUP{i}_AWAY"] = away
        context[f"MATCHUP{i}_HS"]   = hs
        context[f"MATCHUP{i}_AS"]   = aS
        context[f"MATCHUP{i}_BLURB"] = blurb

        context[f"MATCHUP{i}_TOP_HOME"] = top_home
        context[f"MATCHUP{i}_TOP_AWAY"] = top_away
        context[f"MATCHUP{i}_BUST"]     = bust
        context[f"MATCHUP{i}_KEYPLAY"]  = keyplay
        context[f"MATCHUP{i}_DEF"]      = dnote

        # legacy/compat convenience
        try:
            hs_f = float(hs) if hs not in ("", None) else float("nan")
            as_f = float(aS) if aS not in ("", None) else float("nan")
            if hs not in ("", None) and aS not in ("", None):
                scoreline = f"{home} {int(hs_f) if hs_f == int(hs_f) else hs_f} – {away} {int(as_f) if as_f == int(as_f) else as_f}"
                winner = home if hs_f >= as_f else away
                loser  = away if hs_f >= as_f else home
                headline = f"{winner} def. {loser}"
            else:
                scoreline = f"{home} vs {away}".strip()
                headline = scoreline
        except Exception:
            scoreline = f"{home} vs {away}".strip()
            headline = scoreline

        context[f"MATCHUP{i}_TEAMS"]    = scoreline
        context[f"MATCHUP{i}_HEADLINE"] = headline
        context[f"MATCHUP{i}_BODY"]     = blurb


def add_template_synonyms(context: Dict[str, Any], slots: int) -> None:
    """
    Flatten/alias fields that the Word template might reference.
    """
    context["WEEK_NUMBER"] = context.get("week", context.get("week_num", ""))
    if "WEEKLY_INTRO" not in context:
        context["WEEKLY_INTRO"] = context.get("intro", "")

    awards = context.get("awards", {}) or {}
    top_score   = awards.get("top_score", {}) or {}
    low_score   = awards.get("low_score", {}) or {}
    largest_gap = awards.get("largest_gap", {}) or {}

    context["AWARD_TOP_TEAM"]     = top_score.get("team", "")
    context["AWARD_TOP_NOTE"]     = str(top_score.get("points", "")) or ""
    context["AWARD_CUPCAKE_TEAM"] = low_score.get("team", "")
    context["AWARD_CUPCAKE_NOTE"] = str(low_score.get("points", "")) or ""
    context["AWARD_KITTY_TEAM"]   = largest_gap.get("desc", "")
    context["AWARD_KITTY_NOTE"]   = str(largest_gap.get("gap", "")) or ""


def add_logo_images(context: Dict[str, Any], doc: DocxTemplate, max_slots: int, width_mm: int = 25,
                    logo_map: Optional[Dict[str, str]] = None) -> None:
    """
    For each matchup i, set MATCHUPi_HOME_LOGO / MATCHUPi_AWAY_LOGO to InlineImage or a placeholder string.
    """
    for i in range(1, max_slots + 1):
        home = context.get(f"MATCHUP{i}_HOME", "") or ""
        away = context.get(f"MATCHUP{i}_AWAY", "") or ""

        hp = find_logo_path(home) if home else None
        ap = find_logo_path(away) if away else None

        if hp and Path(hp).is_file():
            context[f"MATCHUP{i}_HOME_LOGO"] = InlineImage(doc, hp, width=Mm(width_mm))
            if logo_map is not None: logo_map[home] = hp
        else:
            context[f"MATCHUP{i}_HOME_LOGO"] = "[no-logo]"

        if ap and Path(ap).is_file():
            context[f"MATCHUP{i}_AWAY_LOGO"] = InlineImage(doc, ap, width=Mm(width_mm))
            if logo_map is not None: logo_map[away] = ap
        else:
            context[f"MATCHUP{i}_AWAY_LOGO"] = "[no-logo]"


def add_branding_images(context: Dict[str, Any], doc: DocxTemplate, cfg: Dict[str, Any]) -> None:
    """Insert league/business logos if provided in leagues.json."""
    # league logo
    league_logo = cfg.get("league_logo")
    league_logo = find_logo_path(league_logo) if league_logo else None
    if league_logo and Path(league_logo).is_file():
        context["LEAGUE_LOGO"] = InlineImage(doc, league_logo, width=Mm(40))
    else:
        context["LEAGUE_LOGO"] = "[no-league-logo]"

    # sponsor/business
    sponsor = cfg.get("sponsor", {}) or {}
    biz_logo = sponsor.get("logo")
    biz_logo = find_logo_path(biz_logo) if biz_logo else None
    if biz_logo and Path(biz_logo).is_file():
        context["BUSINESS_LOGO"] = InlineImage(doc, biz_logo, width=Mm(35))
    else:
        context["BUSINESS_LOGO"] = "[no-biz-logo]"

    context["SPONSOR_NAME"] = sponsor.get("name", "")
    context["SPONSOR_LINE"] = sponsor.get("line", "")
    context["SPONSOR"] = sponsor.get("line", "") or sponsor.get("name", "")


# -------------------- LLM blurbs (with safe fallback) --------------------

BLURB_PROMPT = """You are a sports desk writer crafting vivid weekly fantasy FOOTBALL recaps.
Write a {words}-word, lively but concise game story in plain text (no markdown or emojis).
Include: who won, final fantasy score, the pivotal moment, and 1–2 standout performers.
If any detail is missing, gracefully skip it without inventing facts.

Context:
- Home: {home}  Away: {away}
- Final: {hs}-{away_score}
- Top (Home): {top_home}
- Top (Away): {top_away}
- Biggest Bust: {bust}
- Key Play: {keyplay}
- Defense Note: {dnote}
Tone: energetic local-paper style. Avoid clichés. One tight paragraph.
"""

def default_blurb(g: Dict[str, Any]) -> str:
    home = (g.get("home") or "").strip()
    away = (g.get("away") or "").strip()
    hs   = g.get("hs")
    as_  = g.get("as", g.get("ascore"))
    top_home = (g.get("top_home", g.get("home_top", "")) or "").strip()
    top_away = (g.get("top_away", g.get("away_top", "")) or "").strip()
    keyplay  = (g.get("key_play", g.get("keyplay", "")) or "").strip()

    if hs not in ("", None) and as_ not in ("", None):
        try:
            hs_f = float(hs); as_f = float(as_)
            winner = home if hs_f >= as_f else away
            loser  = away if hs_f >= as_f else home
            first = f"{winner} topped {loser} {int(hs_f) if hs_f.is_integer() else hs_f}-{int(as_f) if as_f.is_integer() else as_f}."
        except Exception:
            first = f"{home} faced {away}."
    else:
        first = f"{home} faced {away}."
    bits = []
    if top_home or top_away:
        stars = ", ".join(x for x in [top_home, top_away] if x)
        bits.append(f"Standouts: {stars}.")
    if keyplay:
        bits.append(f"Key play: {keyplay}.")
    return " ".join([first] + bits).strip()


def maybe_expand_blurbs(ctx: Dict[str, Any], words: int = 160, model: str = "gpt-4o-mini", temperature: float = 0.7) -> None:
    """Replace/augment each game's 'blurb' using an LLM. Never leaves a game blank."""
    api_key = os.getenv("OPENAI_API_KEY")
    games = ctx.get("games", []) or []

    if not api_key:
        print("[warn] --llm-blurbs set but OPENAI_API_KEY not found; using default blurbs.")
        for g in games:
            if not (g.get("blurb") or "").strip():
                g["blurb"] = default_blurb(g)
        return

    try:
        from openai import OpenAI
    except Exception as e:
        print(f"[warn] openai package not available ({e}); using default blurbs.")
        for g in games:
            if not (g.get("blurb") or "").strip():
                g["blurb"] = default_blurb(g)
        return

    client = OpenAI(api_key=api_key)

    for g in games:
        baseline = (g.get("blurb") or "").strip() or default_blurb(g)
        prompt = BLURB_PROMPT.format(
            words=words,
            home=g.get("home",""), away=g.get("away",""),
            hs=g.get("hs",""), away_score=g.get("as","") or g.get("ascore",""),
            top_home=g.get("top_home", g.get("home_top","")),
            top_away=g.get("top_away", g.get("away_top","")),
            bust=g.get("biggest_bust", g.get("bust","")),
            keyplay=g.get("key_play", g.get("keyplay","")),
            dnote=g.get("defense_note", g.get("def","")),
        )
        try:
            resp = client.responses.create(model=model, input=prompt, temperature=temperature)
            text = (getattr(resp, "output_text", None) or "").strip()
            g["blurb"] = text if text else baseline
        except Exception as e:
            try:
                print(f"[warn] LLM blurb failed for {g.get('home','?')} vs {g.get('away','?')}: {e}")
            except UnicodeEncodeError:
                print("[warn] LLM blurb failed (non-ASCII message).")
            g["blurb"] = baseline


# -------------------- Rendering --------------------

def _safe_get_missing(doc: DocxTemplate, ctx: Dict[str, Any]) -> List[str]:
    """Return a best-effort list of undeclared variables; tolerant to docxtpl versions."""
    try:
        missing = doc.get_undeclared_template_variables(ctx)  # newer docxtpl
        return sorted(missing) if missing else []
    except TypeError:
        try:
            missing = doc.get_undeclared_template_variables()  # older docxtpl
            return sorted(missing) if missing else []
        except Exception:
            return []


def render_single_league(cfg: Dict[str, Any], args: argparse.Namespace) -> Tuple[str, Optional[str], Dict[str, str]]:
    """Render one league; returns (docx_path, pdf_path_or_None, logo_map)."""
    league_id = cfg.get("league_id")
    year      = cfg.get("year")
    espn_s2   = cfg.get("espn_s2", "")
    swid      = cfg.get("swid", "")

    if args.branding_test:
        # Minimal context just to test logos/template — no ESPN call.
        ctx: Dict[str, Any] = {
            "week": args.week_label or "Branding Test",
            "date": args.date or "",
            "games": [],
        }
    else:
        raw_games = fetch_week_from_espn(league_id, year, espn_s2, swid, force_week=args.week)
        games = adapt_games_for_build_context(raw_games)
        ctx = build_context(cfg, games)

        # Optional overrides from CLI
        if args.week is not None:  ctx["week_num"] = args.week
        if args.week_label:        ctx["week"] = args.week_label
        if args.date:              ctx["date"] = args.date

        # Expand blurbs (with fallback)
        if args.llm_blurbs:
            maybe_expand_blurbs(ctx, words=args.blurb_words, model=args.model, temperature=args.temperature)

    # Per-matchup keys + synonyms + branding
    add_enumerated_matchups(ctx, max_slots=args.slots)
    doc = DocxTemplate(args.template)

    logo_map: Dict[str, str] = {}
    add_logo_images(ctx, doc, max_slots=args.slots, width_mm=args.logo_mm, logo_map=logo_map)
    add_template_synonyms(ctx, slots=args.slots)
    add_branding_images(ctx, doc, cfg)

    # Helpful warning during template editing
    missing = _safe_get_missing(doc, ctx)
    if missing:
        print(f"[warn] Template references unknown variables: {missing}")

    # Output paths
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


# -------------------- CLI --------------------

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", default="leagues.json", help="Path to leagues config JSON.")
    ap.add_argument("--template", default="recap_template.docx", help="DOCX template to render.")
    ap.add_argument("--out-dir", default="recaps", help="Output root directory.")
    ap.add_argument("--pdf", action="store_true", help="Also export PDF (via LibreOffice/docx2pdf).")

    ap.add_argument("--league", default=None, help="Only render the league with this name.")
    ap.add_argument("--week", type=int, default=None, help="Force a specific completed week number.")
    ap.add_argument("--week-label", default=None, help='Override week label, e.g. "Week 1 (Sep 4–9, 2025)".')
    ap.add_argument("--date", default=None, help="Override date label text.")
    ap.add_argument("--slots", type=int, default=10, help="Max matchup slots to render.")
    ap.add_argument("--logo-mm", type=int, default=25, help="Logo width in millimeters.")
    ap.add_argument("--print-logo-map", action="store_true", help="Print which logo file each team used.")
    ap.add_argument("--branding-test", action="store_true", help="Render a minimal doc to verify logos/template (no ESPN).")

    # LLM blurbs
    ap.add_argument("--llm-blurbs", action="store_true", help="Generate longer blurbs with OpenAI.")
    ap.add_argument("--blurb-words", type=int, default=160, help="Target words for LLM blurbs.")
    ap.add_argument("--model", default="gpt-4o-mini", help="OpenAI model for blurbs.")
    ap.add_argument("--temperature", type=float, default=0.7, help="LLM temperature for blurbs.")
    return ap.parse_args()


def main() -> None:
    args = parse_args()

    # Load leagues
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
