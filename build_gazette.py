#!/usr/bin/env python3
"""
build_gazette.py
- Fetch a specific completed ESPN week (private or public leagues)
- Render your DOCX from a Word template (docx/docx/dotx) with logos in header/footer tags:
    {{ league_logo }} and {{ sponsor_logo }}
- Optional: export PDF later in Word (font-accurate)

Usage (single league, explicit week):
  . .venv/bin/activate 2>/dev/null || true
  python build_gazette.py \
    --template recap_template.docx \
    --out-docx recaps/Week1_Gazette.docx \
    --league-id 123456 \
    --year 2024 \
    --week 1 \
    --slots 6 \
    --league-logo logos/generated_logos/BrownSEA_KC.PNG \
    --sponsor-logo logos/generated_logos/gazette_logo.png
"""

import os, sys, json
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
from pathlib import Path
from typing import Any, Dict, List

def _get_first_attr(obj, names, default=None):
    for n in names:
        if hasattr(obj, n):
            v = getattr(obj, n)
            if v is not None:
                return v
    return default

def resolve_last_completed_week(league) -> int:
    cur = _get_first_attr(
        league,
        ["current_week", "currentWeek", "currentMatchupPeriod", "scoringPeriodId"],
        1,
    )
    try:
        cur = int(cur)
    except Exception:
        cur = 1
    last = max(1, cur - 1)
    try:
        reg = int(getattr(league.settings, "reg_season_count", last))
        if last > reg:
            last = reg
    except Exception:
        pass
    return last

# ESPN
try:
    from espn_api.football import League

    def last_completed_week(league):
        # Many leagues expose finalScoringPeriod; otherwise fall back safely.
        try:
            return int(getattr(league, "finalScoringPeriod", None) or league.current_week - 1)
        except Exception:
            return max(1, league.current_week - 1)

    # In your main():
    # if args.week is None:
    #     league = connect_league(league_id, year, espn_s2, swid)  # however you already do this
    #     args.week = last_completed_week(league)

except Exception:
    League = None  # lazy error if not installed


def die(msg: str, code: int = 2):
    print(f"[error] {msg}", file=sys.stderr)
    sys.exit(code)


def require_file(p: Path, label: str):
    if not p.is_file():
        die(f"{label} not found: {p.resolve()}")


def fetch_week(
    league_id: int,
    year: int,
    week: int,
    espn_s2: str | None = None,
    swid: str | None = None,
) -> List[Dict[str, Any]]:
    """
    Returns a list of matchup dicts for the completed week:
      [{'home': 'Team A', 'away': 'Team B', 'home_score': 101.2, 'away_score': 98.6}, ...]
    """
    if League is None:
        die("espn_api not installed. Run: pip install espn_api")

    # Connect (cookie auth only if provided; public leagues work without)
    if espn_s2 and swid:
        lg = League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
    else:
        lg = League(league_id=league_id, year=year)

    # ESPN indexing: scoringPeriodId == week
    matchups = lg.scoreboard(week)
    out = []
    for m in matchups:
        # m.home_team / m.away_team may be objects; try to get names
        def _name(team_obj):
            return getattr(team_obj, "team_name", None) or getattr(team_obj, "name", None) or str(team_obj)

        home = _name(m.home_team)
        away = _name(m.away_team)
        hs = getattr(m, "home_score", None)
        as_ = getattr(m, "away_score", None)
        out.append(
            {
                "home": home,
                "away": away,
                "home_score": hs if hs is not None else 0,
                "away_score": as_ if as_ is not None else 0,
            }
        )
    return out


def build_context(
    week: int,
    slots: int,
    league_logo: Path | None,
    sponsor_logo: Path | None,
    games: List[Dict[str, Any]],
) -> Dict[str, Any]:
    # Trim to requested visible slots (if you want fewer than the league produced)
    games = games[: max(slots, 0)] if slots else games

    ctx: Dict[str, Any] = {
        "week_num": week,
        "games": games,
    }
    if league_logo and league_logo.is_file():
        ctx["LEAGUE_LOGO"] = str(league_logo)
    if sponsor_logo and sponsor_logo.is_file():
        ctx["SPONSOR_LOGO"] = str(sponsor_logo)
    return ctx


def resolve_template(path_str: str) -> Path:
    p = Path(path_str)
    if p.is_file():
        return p
    # search in ./templates if not found
    alt = Path("templates") / p.name
    if alt.is_file():
        return alt
    die(f"Template not found: {p.resolve()}")


def render_docx(template_path, out_docx, ctx, args):
    tpl = DocxTemplate(template_path)

    # Normalize & inject logos (only if present in ctx)
    for key in ("LEAGUE_LOGO", "SPONSOR_LOGO"):
        if key in ctx and ctx[key]:
            ctx[key] = InlineImage(tpl, ctx[key], width=Mm(30))  # tweak size if needed

    tpl.render(ctx)
    tpl.save(out_docx)

    from types import SimpleNamespace
    from docxtpl import InlineImage
    from docx.shared import Mm

    # --- SAFE FALLBACKS (add before tpl.render(ctx)) ---
    # Provide a basic 'league' object with a name, in case template uses {{ league }} or {{ league.name }}
    league_name = ctx.get("title") or ctx.get("LEAGUE_NAME") or "League"
    ctx.setdefault("league", {"name": league_name})  # dict works with {{ league.name }}
    # If your template uses {{ league_logo }} anywhere, give it too:
    if "league_logo" not in ctx and args.league_logo:
        ctx["league_logo"] = InlineImage(tpl, args.league_logo, width=Mm(30))

    # Map your header/footer placeholders exactly as they appear in the .docx
    # (your template shows {{ league-logo-tag }} and {{ sponsor-logo-tag }})
    if args.league_logo:
        ctx["LEAGUE_LOGO"] = InlineImage(tpl, args.league_logo, width=Mm(30))
    if args.sponsor_logo:
        ctx["SPONSOR_LOGO"] = InlineImage(tpl, args.sponsor_logo, width=Mm(30))

        # Optional: ensure week fields exist so {{ WEEK_NUMBER }} etc don’t error
        ctx.setdefault("WEEK_NUMBER", ctx.get("week") or ctx.get("week_num") or "")
        ctx.setdefault("WEEKLY_INTRO", ctx.get("intro", ""))


        tpl.render(ctx)
        tpl.save(str(out_docx))


def main():
    import argparse

    ap = argparse.ArgumentParser(description="Build a Gazette DOCX from ESPN + Word template.")
    ap.add_argument("--template", required=True, help="Path to DOCX/DOTX template (e.g., recap_template.docx)")
    ap.add_argument("--out-docx", required=True, help="Output DOCX path (e.g., recaps/Week1_Gazette.docx)")

    ap.add_argument("--league-id", type=int, required=True, help="ESPN league id")
    ap.add_argument("--year", type=int, required=True, help="League year, e.g., 2024")
    ap.add_argument(
    "--week",
    default="auto",
    help="Completed week to pull (number) or 'auto' to use the last completed week",)
    ap.add_argument("--slots", type=int, default=6, help="How many matchups to show (default 6)")

    ap.add_argument("--league-logo", default=None, help="Path to league logo image")
    ap.add_argument("--sponsor-logo", default=None, help="Path to sponsor logo image")

    ap.add_argument(
    "--blurbs",
    dest="blurbs",
    action="store_true",
    default=False,
    help="Enable LLM blurbs (or template-generated fallbacks)",)

    ap.add_argument(
    "--no-blurbs",
    dest="blurbs",
    action="store_false",
    help="Disable blurbs",)

    ap.add_argument("--blurb-words", type=int, default=180)
    ap.add_argument("--temperature", type=float, default=0.4)
    ap.add_argument("--blurb-style", default="mascot", choices=["mascot", "neutral", "hype", "coach"])


    # If your league is private, set cookies via env or flags
    ap.add_argument("--espn-s2", default=os.getenv("ESPN_S2"), help="ESPN_S2 cookie (or set env ESPN_S2)")
    ap.add_argument("--swid", default=os.getenv("SWID"), help="SWID cookie (or set env SWID)")

    args = ap.parse_args()

    template_path = resolve_template(args.template)
    out_docx = Path(args.out_docx)

    league_logo = Path(args.league_logo) if args.league_logo else None
    sponsor_logo = Path(args.sponsor_logo) if args.sponsor_logo else None

    if league_logo:
        require_file(league_logo, "League logo")
    if sponsor_logo:
        require_file(sponsor_logo, "Sponsor logo")

    week_arg = args.week
    if isinstance(week_arg, str) and week_arg.lower() == "auto":
        # Initialize league to resolve last completed week
        if League is None:
            die("espn_api not installed. Run: pip install espn_api")
        if args.espn_s2 and args.swid:
            league = League(league_id=args.league_id, year=args.year, espn_s2=args.espn_s2, swid=args.swid)
        else:
            league = League(league_id=args.league_id, year=args.year)
        use_week = resolve_last_completed_week(league)
    else:
        use_week = int(week_arg)


    games = fetch_week(
        league_id=args.league_id,
        year=args.year,
        week=use_week,
        espn_s2=args.espn_s2,
        swid=args.swid,
    )

    ctx = build_context(
        week=use_week,
        slots=args.slots,
        league_logo=league_logo,
        sponsor_logo=sponsor_logo,
        games=games,
    )

    ctx["blurbs_enabled"] = bool(args.blurbs)
    ctx["blurb_style"] = args.blurb_style
    ctx["blurb_words"] = int(args.blurb_words)
    ctx["blurb_temperature"] = float(args.temperature)

    # Ensure every slot has a 'blurb' field so the template never breaks.
    # If you already have a list like ctx["matchups"] or ctx["slots"], adapt the name below.
    matchups = ctx.get("matchups") or ctx.get("slots") or []
    for m in matchups:
        if "blurb" not in m or not m["blurb"]:
            home = m.get("home_name") or m.get("home") or "Home"
            away = m.get("away_name") or m.get("away") or "Away"
            hs = m.get("home_score", "")
            as_ = m.get("away_score", "")
            style = ctx["blurb_style"]
            m["blurb"] = f"{style.capitalize()} recap: {home} {hs} vs {away} {as_}. Highlights coming soon."

    render_docx(template_path, out_docx, ctx, args)
    print(f"[ok] Wrote DOCX: {out_docx.resolve()}")


if __name__ == "__main__":
    main()
