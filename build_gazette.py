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
from pathlib import Path
from typing import Any, Dict, List

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

# ESPN
try:
    from espn_api.football import League
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
        ctx["league_logo"] = str(league_logo)
    if sponsor_logo and sponsor_logo.is_file():
        ctx["sponsor_logo"] = str(sponsor_logo)
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


def render_docx(template_path: Path, out_docx: Path, ctx: Dict[str, Any]):
    out_docx.parent.mkdir(parents=True, exist_ok=True)
    tpl = DocxTemplate(str(template_path))

    # If your template uses InlineImage for any image placeholders you can do:
    # Convert string file paths to InlineImage with a default size (keeps aspect).
    for key in ("league_logo", "sponsor_logo"):
        if key in ctx and isinstance(ctx[key], str) and Path(ctx[key]).is_file():
            ctx[key] = InlineImage(tpl, ctx[key], width=Mm(30))  # tweak size to your header/footer

    tpl.render(ctx)
    tpl.save(str(out_docx))


def main():
    import argparse

    ap = argparse.ArgumentParser(description="Build a Gazette DOCX from ESPN + Word template.")
    ap.add_argument("--template", required=True, help="Path to DOCX/DOTX template (e.g., recap_template.docx)")
    ap.add_argument("--out-docx", required=True, help="Output DOCX path (e.g., recaps/Week1_Gazette.docx)")

    ap.add_argument("--league-id", type=int, required=True, help="ESPN league id")
    ap.add_argument("--year", type=int, required=True, help="League year, e.g., 2024")
    ap.add_argument("--week", type=int, required=True, help="Completed week number to pull")
    ap.add_argument("--slots", type=int, default=6, help="How many matchups to show (default 6)")

    ap.add_argument("--league-logo", default=None, help="Path to league logo image")
    ap.add_argument("--sponsor-logo", default=None, help="Path to sponsor logo image")

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

    games = fetch_week(
        league_id=args.league_id,
        year=args.year,
        week=args.week,
        espn_s2=args.espn_s2,
        swid=args.swid,
    )

    ctx = build_context(
        week=args.week,
        slots=args.slots,
        league_logo=league_logo,
        sponsor_logo=sponsor_logo,
        games=games,
    )

    render_docx(template_path, out_docx, ctx)
    print(f"[ok] Wrote DOCX: {out_docx.resolve()}")


if __name__ == "__main__":
    main()
