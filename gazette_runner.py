#!/usr/bin/env python3
"""
Generate styled Weekly Gazette DOCX/PDF files for one or many leagues.

- Reads leagues from --leagues (default: leagues.json)
- Pulls matchup data via gazette_data.fetch_week_from_espn (unless --branding-test)
- Builds context via gazette_data.build_context
- Adds MATCHUPi_* keys, league/sponsor branding, and InlineImage logos
- Renders with docxtpl and (optionally) converts to PDF via LibreOffice/Word

Examples:
  python3 gazette_runner.py --slots 10 --pdf
  python3 gazette_runner.py --league "My League" --week 1 --slots 8
  python3 gazette_runner.py --branding-test --print-logo-map
"""

from __future__ import annotations
from types import SimpleNamespace


import argparse
import json
import os
import re
import sys
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

# Local deps
try:
    from gazette_data import build_context, fetch_week_from_espn
except Exception:
    print("[error] Unable to import gazette_data. Activate your venv and run from the repo root.", file=sys.stderr)
    raise

# --- optional mascot mapping (safe fallback if missing) ---
try:
    from mascots_util import logo_for as lookup_logo
except Exception:
    def lookup_logo(_: str) -> Optional[str]:
        return None
    

# --- replace your existing BLURB_PROMPT + maybe_expand_blurbs with this ---

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

def default_blurb(g: dict) -> str:
    home = (g.get("home") or "").strip()
    away = (g.get("away") or "").strip()
    hs   = g.get("hs")
    as_  = g.get("as")
    top_home = (g.get("top_home") or "").strip()
    top_away = (g.get("top_away") or "").strip()
    keyplay  = (g.get("keyplay") or "").strip()

    # Headline-ish first sentence
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

    # Add quick color
    bits = []
    if top_home or top_away:
        stars = ", ".join(x for x in [top_home, top_away] if x)
        bits.append(f"Standouts: {stars}.")
    if keyplay:
        bits.append(f"Key play: {keyplay}.")

    return " ".join([first] + bits).strip()


def maybe_expand_blurbs(ctx, words: int = 160, model: str = "gpt-4o-mini", temperature: float = 0.7):
    """Replace/augment each game's 'blurb' using an LLM. Requires OPENAI_API_KEY."""
    import os
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[warn] --llm-blurbs set but OPENAI_API_KEY not found; using default blurbs.")
        # ensure we have *something*
        for g in ctx.get("games", []) or []:
            if not (g.get("blurb") or "").strip():
                g["blurb"] = default_blurb(g)
        return

    try:
        from openai import OpenAI
    except Exception as e:
        print(f"[warn] openai package not available ({e}); using default blurbs.")
        for g in ctx.get("games", []) or []:
            if not (g.get("blurb") or "").strip():
                g["blurb"] = default_blurb(g)
        return

    client = OpenAI(api_key=api_key)
    games = ctx.get("games", []) or []
    for g in games:
        # baseline so we always have something
        baseline = (g.get("blurb") or "").strip() or default_blurb(g)

        try:
            prompt = BLURB_PROMPT.format(
                words=words,
                home=g.get("home",""), away=g.get("away",""),
                hs=g.get("hs",""), away_score=g.get("as",""),
                top_home=g.get("top_home",""), top_away=g.get("top_away",""),
                bust=g.get("bust",""), keyplay=g.get("keyplay",""), dnote=g.get("def","")
            )
            resp = client.responses.create(
                model=model,
                input=prompt,
                temperature=temperature,
            )
            text = (resp.output_text or "").strip()
            g["blurb"] = text if text else baseline
        except Exception as e:
            # keep the baseline; avoid noisy Unicode errors on some terminals
            try:
                print(f"[warn] LLM blurb failed for {g.get('home','?')} vs {g.get('away','?')}: {e}")
            except UnicodeEncodeError:
                print("[warn] LLM blurb failed (non-ASCII message).")
            g["blurb"] = baseline


# ---------------- PDF helpers ----------------

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

LOGO_DIRS: List[str] = [
    "logos/sponsors",        # sponsor logos (if you add them here)
    "logos/ai",
    "logos/generated_logos",
    "logos/generated_logo",
    "logos",
]

def _sanitize_name(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    return re.sub(r"_+", "_", base)


def find_logo_path(team_or_name: str) -> Optional[str]:
    """
    1) mascots_util mapping, then
    2) scan known dirs for a likely filename match (sanitized, then loose match)
    """
    try:
        p = lookup_logo(team_or_name)
        if p and Path(p).is_file():
            return str(Path(p).resolve())
    except Exception:
        pass

    candidates: List[Path] = []
    sanitized = _sanitize_name(team_or_name).lower()
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
            if f.is_file() and f.suffix.lower() in exts and sanitized in f.stem.lower():
                candidates.append(f.resolve())

    if candidates:
        return str(sorted(candidates, key=lambda p: len(p.name))[0])
    return None


def add_logo_images(context: Dict[str, Any], doc: DocxTemplate, max_slots: int,
                    width_mm: int = 25, logo_map: Optional[Dict[str, str]] = None) -> None:
    """
    Inject InlineImage objects for each matchup's home/away team.
    Adds MATCHUPi_HOME_LOGO and MATCHUPi_AWAY_LOGO.
    """
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
    """
    Explode context['games'] -> MATCHUPi_* keys used by the Word template.
    Also fills a safe fallback for a stray {{ MATCHUP }} token if present in template.
    """
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

        # extras for nice scoreline/headline if you ever use them elsewhere
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
            headline  = scoreline

        context[f"MATCHUP{i}_TEAMS"]    = scoreline
        context[f"MATCHUP{i}_HEADLINE"] = headline
        context[f"MATCHUP{i}_BODY"]     = blurb

    # your template has a bare {{ MATCHUP }} token; keep it safe as empty
    context.setdefault("MATCHUP", "")


def add_template_synonyms(context: Dict[str, Any], slots: int) -> None:
    """
    Flatten award structures and add aliases your Word template expects.
    """
    # WEEK_NUMBER / WEEKLY_INTRO for the template header/body
    context["WEEK_NUMBER"] = context.get("week", context.get("week_num", ""))
    context.setdefault("WEEKLY_INTRO", context.get("intro", ""))

    awards = context.get("awards", {}) or {}
    top_score   = awards.get("top_score", {}) or {}
    low_score   = awards.get("low_score", {}) or {}
    largest_gap = awards.get("largest_gap", {}) or {}
    play_note   = awards.get("play_of_week", "") or awards.get("play_note", "")
    mgr_note    = awards.get("manager_move", "") or awards.get("manager_note", "")

    context["AWARD_TOP_TEAM"]      = top_score.get("team", "")
    context["AWARD_TOP_NOTE"]      = str(top_score.get("points", "")) or ""
    context["AWARD_CUPCAKE_TEAM"]  = low_score.get("team", "")
    context["AWARD_CUPCAKE_NOTE"]  = str(low_score.get("points", "")) or ""
    context["AWARD_KITTY_TEAM"]    = largest_gap.get("desc", "")
    context["AWARD_KITTY_NOTE"]    = str(largest_gap.get("gap", "")) or ""
    context["AWARD_PLAY_NOTE"]     = play_note
    context["AWARD_MANAGER_NOTE"]  = mgr_note

    # FOOTER_NOTE if your template uses it
    context.setdefault("FOOTER_NOTE", "")


def add_branding(ctx: Dict[str, Any], doc: DocxTemplate, cfg: Dict[str, Any], logo_mm: int = 30) -> Dict[str, str]:
    """
    Populate:
      - LEAGUE_LOGO   (InlineImage | "[no-logo]")
      - BUSINESS_LOGO (InlineImage | "[no-logo]")  # your template's bottom logo
      - SPONSOR       (string line shown in footer)
      - title         (nice page title if template uses it)
    Also returns a logo_map of what file paths were used.
    """
    logo_map: Dict[str, str] = {}

    def _image_or_placeholder(path: Optional[str], key: str) -> Any:
        if path and Path(path).is_file():
            logo_map[key] = str(Path(path).resolve())
            return InlineImage(doc, path, width=Mm(logo_mm))
        return "[no-logo]"

    league_name = cfg.get("name") or cfg.get("short_name") or ""
    league_logo = cfg.get("league_logo") or find_logo_path(league_name)
    ctx["LEAGUE_LOGO"] = _image_or_placeholder(league_logo, f"LEAGUE:{league_name}")

    sponsor = cfg.get("sponsor", {}) or {}
    sponsor_logo = sponsor.get("logo") or find_logo_path(sponsor.get("name", "") or "sponsor")
    ctx["BUSINESS_LOGO"] = _image_or_placeholder(sponsor_logo, f"SPONSOR:{sponsor.get('name','').strip()}")
    # Your template uses {{SPONSOR}} as text:
    sponsor_line = sponsor.get("line") or sponsor.get("name") or ""
    ctx["SPONSOR"] = sponsor_line

    # Optional title if your first line uses {{ title }}
    week_label = ctx.get("week") or f"Week {ctx.get('week_num','')}".strip()
    ctx.setdefault("title", f"Gridiron Gazette — {week_label}".strip(" —"))

    return logo_map

from types import SimpleNamespace

def adapt_games_for_build_context(games_list):
    """
    Normalize game dicts/objects so build_context can do attribute access:
    g.home, g.away, g.hs, g.ascore, g.home_top, g.away_top, g.bust, g.keyplay, g.dnote, etc.
    """
    def coerce_num(x):
        try:
            return float(x)
        except Exception:
            return x

    out = []
    for g in (games_list or []):
        if isinstance(g, dict):
            # team names
            home = g.get("home") or g.get("home_team") or ""
            away = g.get("away") or g.get("away_team") or ""

            # scores (provide many aliases)
            hs = coerce_num(g.get("hs", g.get("home_score", g.get("hscore", g.get("score_home", "")))))
            a  = coerce_num(g.get("as", g.get("away_score", g.get("ascore", g.get("score_away", "")))))

            # spotlights & notes (alias all the likely variants)
            top_home = g.get("top_home", g.get("home_top", ""))
            top_away = g.get("top_away", g.get("away_top", ""))
            bust     = g.get("bust", g.get("bust_player", ""))
            keyplay  = g.get("keyplay", g.get("key_play", ""))
            dnote    = g.get("def", g.get("dnote", g.get("defense", g.get("defense_note", ""))))
            blurb    = g.get("blurb", "")

            out.append(SimpleNamespace(
                # canonical
                home=home, away=away,
                hs=hs, ascore=a,
                # score aliases
                hscore=hs, home_score=hs, score_home=hs,
                away_score=a, score_away=a,
                # spotlight aliases
                home_top=top_home, away_top=top_away,
                top_home=top_home, top_away=top_away,
                bust=bust, bust_player=bust,
                keyplay=keyplay, key_play=keyplay,
                dnote=dnote, defense=dnote, defense_note=dnote,
                # text
                blurb=blurb,
            ))
        else:
            # object from espn_api – ensure a couple of critical aliases exist
            if not hasattr(g, "ascore") and hasattr(g, "away_score"):
                setattr(g, "ascore", getattr(g, "away_score"))
            if not hasattr(g, "hs") and hasattr(g, "home_score"):
                setattr(g, "hs", getattr(g, "home_score"))
            if not hasattr(g, "home_top") and hasattr(g, "top_home"):
                setattr(g, "home_top", getattr(g, "top_home"))
            if not hasattr(g, "away_top") and hasattr(g, "top_away"):
                setattr(g, "away_top", getattr(g, "top_away"))
            out.append(g)
    return out





# ---------------- Rendering ------------------

def safe_title(s: str) -> str:
    s = re.sub(r"[^\w\s\-\(\)\._]", "_", s)
    return re.sub(r"\s+", "_", s).strip("_")


def render_single_league(cfg: Dict[str, Any], args: argparse.Namespace) -> Tuple[str, Optional[str], Dict[str, str]]:
    """
    Render one league's gazette. Returns (docx_path, pdf_path_or_None, logo_map).
    """
    league_id = cfg.get("league_id")
    year      = cfg.get("year")
    espn_s2   = cfg.get("espn_s2", "")
    swid      = cfg.get("swid", "")
    raw_games = fetch_week_from_espn(league_id, year, espn_s2, swid, force_week=args.week)
    games = adapt_games_for_build_context(raw_games)
    ctx = build_context(cfg, games)

    if args.llm_blurbs:
        maybe_expand_blurbs(ctx, words=args.blurb_words, model=args.model, temperature=args.temperature)


    if args.branding_test:
        # Minimal context just to prove branding & layout without ESPN calls
        base_ctx = {
            "week": args.week_label or "Week 1",
            "week_num": args.week or 1,
            "intro": "This is a branding test page to verify logos and layout.",
            "games": [],
            "awards": {},
            "date": args.date or "",
        }
        ctx = base_ctx
    else:
        games = fetch_week_from_espn(league_id, year, espn_s2, swid, force_week=args.week)
        ctx = build_context(cfg, games)

    # CLI overrides
    if args.week is not None:
        ctx["week_num"] = args.week
    if args.week_label:
        ctx["week"] = args.week_label
    if args.date:
        ctx["date"] = args.date

    # Expand games & synonyms
    add_enumerated_matchups(ctx, max_slots=args.slots)
    doc = DocxTemplate(args.template)

    # Per-matchup logos + top branding
    add_logo_images(ctx, doc, max_slots=args.slots, width_mm=args.logo_mm)
    logo_map = add_branding(ctx, doc, cfg, logo_mm=args.logo_mm)
    add_template_synonyms(ctx, slots=args.slots)

    # Helpful when editing templates. Use named 'context' to dodge older docxtpl quirks.
    try:
        missing = doc.get_undeclared_template_variables(context=ctx)  # some versions accept the named arg
        if missing:
            print(f"[warn] Template references unknown variables: {sorted(missing)}")
    except Exception as e:
        print(f"[warn] Skipping undeclared-vars check ({e.__class__.__name__}: {e})")

    # Output
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
        for k, v in sorted(logo_map.items()):
            print(f"  - {k} -> {v}")

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
    ap.add_argument("--print-logo_map", dest="print_logo_map", action="store_true", help="Print which logo file was used.")
    ap.add_argument("--branding-test", action="store_true", help="Skip ESPN fetch; render branding-only context.")
    ap.add_argument("--llm-blurbs", action="store_true", help="Generate longer blurbs with OpenAI.")
    ap.add_argument("--blurb-words", type=int, default=160, help="Target words for LLM blurbs.")
    ap.add_argument("--model", default="gpt-4o-mini", help="OpenAI model for blurbs.")
    ap.add_argument("--temperature", type=float, default=0.7, help="LLM temperature for blurbs.")

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
