from __future__ import annotations
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from espn_api.football import League


# --------- helpers ---------
def _env(name: str, alt: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    if v is None or v == "":
        if alt:
            v = os.getenv(alt)
    return v or None

def _fmt(x: Optional[float]) -> str:
    return f"{float(x):.2f}" if x is not None else ""

def _safe(s: Any) -> str:
    return "" if s is None else str(s)

def _load_team_logos(json_path: Optional[str]) -> Dict[str, str]:
    """
    Optional team logo mapping. File should be {"Team Name": "https://.../logo.png", ...}
    Environment var TEAM_LOGOS_FILE can point to it; otherwise returns {}.
    """
    if not json_path:
        return {}
    p = Path(json_path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

# --------- data shape we assemble from ESPN ---------
@dataclass
class MatchRow:
    home_name: str
    away_name: str
    home_score: float
    away_score: float
    winner: str
    loser: str
    gap: float
    # “spotlight” fields the template expects (we’ll provide decent defaults)
    top_home: str = ""
    top_away: str = ""
    bust: str = ""
    keyplay: str = ""
    def_note: str = ""


def _fetch_rows(league: League, week: int) -> List[MatchRow]:
    rows: List[MatchRow] = []
    matchups = league.scoreboard(week=week)
    for m in matchups:
        home = m.home_team.team_name
        away = m.away_team.team_name
        hs = float(m.home_score or 0.0)
        as_ = float(m.away_score or 0.0)
        winner = home if hs >= as_ else away
        loser = away if winner == home else home
        gap = abs(hs - as_)

        # Attempt “top scorer” from lineups; fall back to blank
        def _top(lineup):
            lineup = lineup or []
            lineup = [p for p in lineup if getattr(p, "points", None) is not None]
            lineup.sort(key=lambda p: p.points, reverse=True)
            if lineup:
                p = lineup[0]
                return f"{getattr(p, 'name', 'Top Player')} — {p.points:.1f}"
            return ""

        top_home = _top(getattr(m, "home_lineup", []))
        top_away = _top(getattr(m, "away_lineup", []))

        # You can customize these simple defaults later if you compute them elsewhere
        bust = ""      # left as empty so Sabre’s recap carries the humor
        keyplay = ""   # (optional extra line in template)
        def_note = ""  # (optional extra line in template)

        rows.append(MatchRow(
            home_name=home, away_name=away,
            home_score=hs, away_score=as_,
            winner=winner, loser=loser, gap=gap,
            top_home=top_home, top_away=top_away,
            bust=bust, keyplay=keyplay, def_note=def_note
        ))
    return rows


def _awards(rows: List[MatchRow]) -> Dict[str, Any]:
    """Compute awards for the template’s tokens."""
    if not rows:
        return {
            "AWARD_CUPCAKE_TEAM": "", "AWARD_CUPCAKE_NOTE": "",
            "AWARD_KITTY_TEAM": "", "AWARD_KITTY_NOTE": "",
            "AWARD_TOP_TEAM": "", "AWARD_TOP_NOTE": "",
            # keep your old single-line variants too if other code uses them
            "CUPCAKE_LINE": "—", "KITTY_LINE": "—", "TOPSCORE_LINE": "—",
        }

    all_team_scores: List[Tuple[str, float]] = []
    kitty_candidates: List[Tuple[str, str, float]] = []
    for r in rows:
        all_team_scores.extend([(r.home_name, r.home_score), (r.away_name, r.away_score)])
        kitty_candidates.append((r.winner, r.loser, r.gap))

    cupcake_team, cupcake_pts = min(all_team_scores, key=lambda x: x[1])
    top_team, top_pts = max(all_team_scores, key=lambda x: x[1])
    kitty_winner, kitty_loser, kitty_gap = max(kitty_candidates, key=lambda x: x[2])

    return {
        # tokens the docx renders:
        "AWARD_CUPCAKE_TEAM": cupcake_team,
        "AWARD_CUPCAKE_NOTE": f"{cupcake_pts:.2f}",
        "AWARD_KITTY_TEAM": kitty_loser,
        "AWARD_KITTY_NOTE": f"fell to {kitty_winner} by {kitty_gap:.2f}",
        "AWARD_TOP_TEAM": top_team,
        "AWARD_TOP_NOTE": f"{top_pts:.2f}",
        # optional legacy single-line variants if elsewhere in code:
        "CUPCAKE_LINE": f"{cupcake_team} — {cupcake_pts:.2f}",
        "KITTY_LINE": f"{kitty_loser} fell to {kitty_winner} by {kitty_gap:.2f}",
        "TOPSCORE_LINE": f"{top_team} — {top_pts:.2f}",
    }


def build_context(league_id: int, year: int, week: int) -> Dict[str, Any]:
    """
    Fetch ESPN data and assemble a context dict with EVERYTHING your template needs.
    - Reads S2/SWID cookies from env (ESPN_S2 / ESPN_SWID, or S2 / SWID)
    - Optionally maps logos from TEAM_LOGOS_FILE (JSON)
    """
    s2 = _env("ESPN_S2", "S2")
    swid = _env("ESPN_SWID", "SWID")
    if not s2 or not swid:
        raise RuntimeError("Missing ESPN cookies: set ESPN_S2 and ESPN_SWID.")

    lg = League(league_id=league_id, year=year, espn_s2=s2, swid=swid)
    wk = int(week or lg.current_week)
    rows = _fetch_rows(lg, wk)

    logos = _load_team_logos(os.getenv("TEAM_LOGOS_FILE"))

    ctx: Dict[str, Any] = {
        # global
        "LEAGUE_ID": league_id,
        "LEAGUE_NAME": getattr(getattr(lg, "settings", None), "name", None) or "League",
        "WEEK_NUMBER": wk,
        "YEAR": year,
        "title": f"{year} — Week {wk}",

        # optional header/footer/sponsor (safe blanks)
        "LEAGUE_LOGO": _safe(os.getenv("LEAGUE_LOGO") or ""),
        "SPONSOR_LOGO": _safe(os.getenv("SPONSOR_LOGO") or ""),
        "SPONSOR_LINE": _safe(os.getenv("SPONSOR_LINE") or ""),
        "FOOTER_NOTE":  _safe(os.getenv("FOOTER_NOTE") or ""),
    }

    # Per-matchup tokens
    for i, r in enumerate(rows, start=1):
        ctx[f"MATCHUP{i}_HOME"] = r.home_name
        ctx[f"MATCHUP{i}_AWAY"] = r.away_name
        ctx[f"MATCHUP{i}_HS"] = _fmt(r.home_score)
        ctx[f"MATCHUP{i}_AS"] = _fmt(r.away_score)

        # logos (if provided in mapping)
        ctx[f"MATCHUP{i}_HOME_LOGO"] = logos.get(r.home_name, "")
        ctx[f"MATCHUP{i}_AWAY_LOGO"] = logos.get(r.away_name, "")

        # Spotlight lines (template’s “Stats Spotlight”)
        ctx[f"MATCHUP{i}_TOP_HOME"] = r.top_home
        ctx[f"MATCHUP{i}_TOP_AWAY"] = r.top_away
        ctx[f"MATCHUP{i}_BUST"] = r.bust
        ctx[f"MATCHUP{i}_KEYPLAY"] = r.keyplay
        ctx[f"MATCHUP{i}_DEF"] = r.def_note

        # Ensure a placeholder exists for the big recap text
        ctx.setdefault(f"MATCHUP{i}_BLURB", "")

    # Awards block
    ctx.update(_awards(rows))

    # Friendly intro if none is set elsewhere
    ctx.setdefault("WEEKLY_INTRO", f"Week {wk} delivered its usual chaos, comedy, and a few miracles.")

    # Count (handy)
    ctx["MATCHUP_COUNT"] = len(rows)

    return ctx
