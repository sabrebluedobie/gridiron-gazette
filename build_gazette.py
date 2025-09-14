#!/usr/bin/env python3
"""
build_gazette.py — render a Weekly Gazette DOCX from ESPN data + a Word template.

Usage (example):
  python build_gazette.py \
    --template recap_template.docx \
    --out-docx recaps/Week1_Gazette.docx \
    --league-id 887998 \
    --year 2025 \
    --week 1 \
    --slots 6 \
    --league-logo logos/generated_logos/BrownSEA_KC.PNG \
    --sponsor-logo logos/generated_logos/gazette_logo.png \
    --llm-blurbs \
    --blurb-style mascot \
    --blurb-words 120 \
    --temperature 0.4

Notes:
- If --week is omitted, we try to use (league.current_week - 1), clamped to >= 1.
- Your template must use underscores in variable names. For the header/footer images,
  change `{{ league-logo-tag }}` -> `{{ league_logo_tag }}` and
          `{{ sponsor-logo-tag }}` -> `{{ sponsor_logo_tag }}`.
"""
from __future__ import annotations

import os

def get_openai_key():
    return os.getenv("OPENAI_API_KEY")

def get_env_var(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise EnvironmentError(f"Missing required environment variable: {name}")
    return val

import argparse
import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional


# Word templating + inline images
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

# Images
from PIL import Image  # noqa: F401 (ensures Pillow present)

# ESPN

import espn_api # noqa: F401 (ensures espn_api present)
try:
    from espn_api.football import League
except Exception as e:
    raise SystemExit(
        "Error: espn_api not installed. Run: pip install espn_api\n"
        f"Details: {e}"
    )


# ---------- Helpers ----------

def last_completed_week(league: League) -> int:
    """
    Best-effort: ESPN libraries expose `current_week` (the week that is now active).
    For a "completed week", we use max(1, current_week - 1).
    If attribute missing, default to 1.
    """
    wk = getattr(league, "current_week", None)
    if isinstance(wk, int) and wk > 1:
        return wk - 1
    return 1


def safe_title(s: str) -> str:
    return "".join(c if c.isalnum() or c in "._- " else "_" for c in (s or ""))


def ensure_image(path: Optional[str]) -> Optional[Path]:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Image not found: {p.resolve()}")
    return p


def inline_logo(tpl: DocxTemplate, image_path: Optional[Path], width_mm: int = 30):
    if not image_path:
        return ""
    return InlineImage(tpl, str(image_path), width=Mm(width_mm))


def get_completed_score(matchup) -> Dict[str, Any]:
    """
    Normalize an ESPN matchup for template fields.
    Works for regular season H/A results.
    """
    # Home/Away team objects differ a bit across API versions; guard with getattr
    home = getattr(matchup, "home_team", None)
    away = getattr(matchup, "away_team", None)

    home_name = getattr(home, "team_name", None) or getattr(home, "team_abbrev", "") or "Home"
    away_name = getattr(away, "team_name", None) or getattr(away, "team_abbrev", "") or "Away"

    # Scores
    home_score = getattr(matchup, "home_score", None)
    away_score = getattr(matchup, "away_score", None)

    # Simple “top scorer” placeholders (customize if you like later)
    top_home = f"{home_name} top performer"
    top_away = f"{away_name} top performer"

    return {
        "home": home_name,
        "away": away_name,
        "hs": f"{home_score:.1f}" if isinstance(home_score, (int, float)) else "",
        "as": f"{away_score:.1f}" if isinstance(away_score, (int, float)) else "",
        "top_home": top_home,
        "top_away": top_away,
        "bust": "",
        "keyplay": "",
        "def": "",
    }


def build_blurb(home: str, away: str, style: str, words: int) -> str:
    """
    Simple, local blurb generator (no LLM call here). You can replace this
    with a real model later if desired.
    """
    if style.lower() == "mascot":
        return (
            f"In a mascot melee, {home} locked horns with {away}. "
            f"Both sides traded blows, but only one walked off with bragging rights. "
            f"Fans are already circling next week on the calendar."
        )
    # default neutral
    return (
        f"{home} and {away} squared off in a tightly contested matchup. "
        f"Momentum swung multiple times before the final whistle."
    )


def fetch_week(league_id: int, year: int, espn_s2: str | None, swid: str | None, week: Optional[int]) -> Dict[str, Any]:
    """
    Connect to ESPN and return (league, week_used, matchups_for_week).
    """
    league = League(league_id=league_id, year=year, espn_s2=espn_s2 or None, swid=swid or None)
    use_week = week or last_completed_week(league)
    # League.matchups property supports filtering by week in recent espn_api versions
    matchups = [m for m in league.matchups if getattr(m, "week", None) == use_week] or league.matchups
    # If above returns empty, fall back to whatever the library exposes
    if getattr(matchups[0], "week", None) != use_week:
        # final fallback: ask the library again via private helper if available
        pass
    return {"league": league, "week": use_week, "matchups": matchups}


def build_context(
    tpl: DocxTemplate,
    league_name: str,
    week_num: int,
    slots: int,
    matchups: List[Any],
    league_logo_path: Optional[Path],
    sponsor_logo_path: Optional[Path],
    llm_blurbs: bool,
    blurb_style: str,
    blurb_words: int,
) -> Dict[str, Any]:
    """
    Convert ESPN data into the flat key structure your DOCX template expects.
    """
    ctx: Dict[str, Any] = {}

    # Header/footer logos (IMPORTANT: your template must use underscores in tag names)
    ctx["league_logo"] = inline_logo(tpl, league_logo_path, width_mm=30)
    ctx["sponsor_logo"] = inline_logo(tpl, sponsor_logo_path, width_mm=30)

    # Top-level fields used by your template
    ctx["title"] = league_name or "Gridiron Gazette"
    ctx["WEEK_NUMBER"] = str(week_num)
    ctx["WEEKLY_INTRO"] = ctx.get("WEEKLY_INTRO", "Here’s how the action unfolded across the league.")

    # Matchups (up to `slots`)
    for i in range(1, slots + 1):
        # Pull matchup or leave blanks
        m = matchups[i - 1] if i - 1 < len(matchups) else None

        key = lambda suffix: f"MATCHUP{i}_{suffix}"

        if not m:
            # blank out the block
            for suffix in [
                "HOME", "AWAY", "HS", "AS", "HOME_LOGO", "AWAY_LOGO",
                "BLURB", "TOP_HOME", "TOP_AWAY", "BUST", "KEYPLAY", "DEF",
            ]:
                ctx[key(suffix)] = "" if suffix not in ("HOME_LOGO", "AWAY_LOGO") else ""
            continue

        norm = get_completed_score(m)
        home = norm["home"]
        away = norm["away"]

        ctx[key("HOME")] = home
        ctx[key("AWAY")] = away
        ctx[key("HS")] = norm["hs"]
        ctx[key("AS")] = norm["as"]
        ctx[key("TOP_HOME")] = norm["top_home"]
        ctx[key("TOP_AWAY")] = norm["top_away"]
        ctx[key("BUST")] = norm["bust"]
        ctx[key("KEYPLAY")] = norm["keyplay"]
        ctx[key("DEF")] = norm["def"]

        # If you later want per-team logos, wire a map here.
        ctx[key("HOME_LOGO")] = ""
        ctx[key("AWAY_LOGO")] = ""

        # Blurb
        ctx[key("BLURB")] = build_blurb(home, away, blurb_style, blurb_words) if llm_blurbs else ""

    # Awards (optional — keep blank if not computed yet)
    ctx["AWARD_CUPCAKE_TEAM"] = ctx.get("AWARD_CUPCAKE_TEAM", "")
    ctx["AWARD_CUPCAKE_NOTE"] = ctx.get("AWARD_CUPCAKE_NOTE", "")
    ctx["AWARD_KITTY_TEAM"] = ctx.get("AWARD_KITTY_TEAM", "")
    ctx["AWARD_KITTY_NOTE"] = ctx.get("AWARD_KITTY_NOTE", "")
    ctx["AWARD_TOP_TEAM"] = ctx.get("AWARD_TOP_TEAM", "")
    ctx["AWARD_TOP_NOTE"] = ctx.get("AWARD_TOP_NOTE", "")

    # Footer bits you referenced
    ctx["FOOTER_NOTE"] = ctx.get("FOOTER_NOTE", dt.date.today().strftime("%b %d, %Y"))
    ctx["SPONSOR_LINE"] = ctx.get("SPONSOR_LINE", "your friendly neighborhood sponsor")

    return ctx


def render_docx(template_path: Path, out_docx: Path, ctx: Dict[str, Any]) -> None:
    tpl = DocxTemplate(str(template_path))
    tpl.render(ctx)
    out_docx.parent.mkdir(parents=True, exist_ok=True)
    tpl.save(str(out_docx))


# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser(description="Render a Weekly Gazette DOCX from ESPN data.")
    ap.add_argument("--template", required=True, help="Path to the Word (.docx) template")
    ap.add_argument("--out-docx", required=True, help="Output DOCX path")
    ap.add_argument("--league-id", type=int, required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--week", type=int, default=None, help="Completed week number; if omitted, uses last completed week")
    ap.add_argument("--slots", type=int, default=6, help="Number of matchup blocks to fill (1–6)")
    ap.add_argument("--league-logo", default=None, help="Path to league logo image for header")
    ap.add_argument("--sponsor-logo", default=None, help="Path to sponsor logo image for footer")

    # Blurb options (local generator placeholder)
    ap.add_argument("--llm-blurbs", action=argparse.BooleanOptionalAction, default=False, help="Fill matchup blurbs")
    ap.add_argument("--blurb-style", default="mascot", help="Blurb style preset (e.g., mascot)")
    ap.add_argument("--blurb-words", type=int, default=120, help="Target words for blurbs (hint only)")
    ap.add_argument("--temperature", type=float, default=0.4, help="Reserved for LLM usage later")

    # Optional display label overrides
    ap.add_argument("--week-label", default=None, help='Override visible week label (e.g., "Week 1 (Sep 4–9, 2025)")')

    # ESPN cookies for private leagues (GH secrets or env can supply these)
    ap.add_argument("--espn-s2", default=None)
    ap.add_argument("--swid", default=None)

    args = ap.parse_args()

    template_path = Path(args.template)
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path.resolve()}")

    out_docx = Path(args.out_docx)

    league_logo = ensure_image(args.league_logo)
    sponsor_logo = ensure_image(args.sponsor_logo)

    data = fetch_week(args.league_id, args.year, args.espn_s2, args.swid, args.week)
    league = data["league"]
    used_week = data["week"]
    matchups = data["matchups"]

    league_name = getattr(league, "settings", None)
    if league_name and hasattr(league.settings, "name"):
        league_name = str(league.settings.name)
    else:
        league_name = f"League {args.league_id}"

    tpl = DocxTemplate(str(template_path))
    ctx = build_context(
        tpl=tpl,
        league_name=league_name,
        week_num=used_week,
        slots=max(1, min(args.slots, 6)),
        matchups=matchups,
        league_logo_path=league_logo,
        sponsor_logo_path=sponsor_logo,
        llm_blurbs=bool(args.llm_blurbs),
        blurb_style=args.blurb_style,
        blurb_words=args.blurb_words,
    )

    # Optional label override
    if args.week_label:
        ctx["WEEK_NUMBER"] = args.week_label

    # Re-init template before rendering/saving (we already used it for InlineImage context sizing)
    tpl = DocxTemplate(str(template_path))
    tpl.render(ctx)
    out_docx.parent.mkdir(parents=True, exist_ok=True)
    tpl.save(str(out_docx))

    print(f"Done: {out_docx.resolve()} (Week {used_week})")


if __name__ == "__main__":
    main()
    