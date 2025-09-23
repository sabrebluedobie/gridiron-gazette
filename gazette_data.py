# gazette_data.py
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from espn_api.football import League

# ---------------------------
# Cookie & league utilities
# ---------------------------

def _read_cookie_pair() -> Tuple[Optional[str], Optional[str]]:
    """Read ESPN cookies from env with multiple common names; normalize SWID."""
    s2 = os.getenv("ESPN_S2") or os.getenv("S2")
    swid = os.getenv("SWID") or os.getenv("ESPN_SWID")
    if swid:
        swid = swid.strip()
        # SWID must be wrapped in braces for espn_api; add if missing
        if not (swid.startswith("{") and swid.endswith("}")):
            swid = "{" + swid.strip("{}") + "}"
    return (s2 if s2 and s2.strip() else None,
            swid if swid and swid.strip() else None)

def get_league(league_id: int, year: int) -> League:
    s2, swid = _read_cookie_pair()
    return League(league_id=league_id, year=year, espn_s2=s2, swid=swid)

def _safe_float(x) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0

def _safe_settings_name(league: League) -> Optional[str]:
    """
    espn_api can expose settings as a dict or an object.
    Try, in order: league.settings.name -> league.settings["name"] -> league.league_name
    """
    try:
        s = getattr(league, "settings", None)
        if s is not None:
            # object-style
            name = getattr(s, "name", None)
            if name:
                return name
            # dict-style
            if isinstance(s, dict):
                name = s.get("name")
                if name:
                    return name
    except Exception:
        pass
    # Older versions sometimes expose league.league_name
    return getattr(league, "league_name", None)

# ---------------------------
# Data structures
# ---------------------------

@dataclass
class TeamGame:
    name: str
    abbrev: str
    score: float
    logo: Optional[str] = None
    top_scorer_name: Optional[str] = None
    top_scorer_pts: Optional[float] = None

@dataclass
class MatchupRow:
    home: TeamGame
    away: TeamGame
    margin: float

@dataclass
class Awards:
    cupcake_team: Optional[str] = None
    cupcake_score: Optional[float] = None
    kitty_loser: Optional[str] = None
    kitty_winner: Optional[str] = None
    kitty_gap: Optional[float] = None
    top_team: Optional[str] = None
    top_score: Optional[float] = None

# ---------------------------
# Fetch week & compute stats
# ---------------------------

def fetch_week_from_espn(league: League, week: int) -> List[MatchupRow]:
    """Fetch scoreboard for week and return normalized rows."""
    rows: List[MatchupRow] = []
    scoreboard = league.scoreboard(week=week)
    for m in scoreboard:
        home_team = m.home_team
        away_team = m.away_team
        hs = _safe_float(m.home_score)
        as_ = _safe_float(m.away_score)
        # abbrev attribute naming varies by version
        def _abbr(t):
            return (
                getattr(t, "abbrev", None)
                or getattr(t, "team_abbrev", None)
                or ""
            )
        rows.append(
            MatchupRow(
                home=TeamGame(
                    name=home_team.team_name,
                    abbrev=_abbr(home_team),
                    score=hs,
                ),
                away=TeamGame(
                    name=away_team.team_name,
                    abbrev=_abbr(away_team),
                    score=as_,
                ),
                margin=abs(hs - as_)
            )
        )
    return rows

def enrich_with_player_tops(league: League, week: int, rows: List[MatchupRow]) -> None:
    """
    Fill top_scorer_name/pts for each team using box_scores.
    If unavailable or API changes, we leave graceful fallback (None).
    """
    try:
        box = league.box_scores(week=week)
    except Exception:
        return

    def best_from_lineup(lineup) -> Tuple[Optional[str], Optional[float]]:
        best_n, best_p = None, None
        for slot in lineup or []:
            pts = _safe_float(getattr(slot, "points", 0.0))
            nm = (
                getattr(slot, "name", None)
                or getattr(getattr(slot, "player", None), "name", None)
                or getattr(slot, "playerName", None)
            )
            if nm is None:
                continue
            if best_p is None or pts > best_p:
                best_p, best_n = pts, nm
        return best_n, best_p

    # Match BoxScore objects to our rows by team name
    for bs in box:
        h_name = getattr(bs.home_team, "team_name", "")
        a_name = getattr(bs.away_team, "team_name", "")
        h_top = best_from_lineup(getattr(bs, "home_lineup", []))
        a_top = best_from_lineup(getattr(bs, "away_lineup", []))
        for r in rows:
            if r.home.name == h_name and r.away.name == a_name:
                r.home.top_scorer_name, r.home.top_scorer_pts = h_top
                r.away.top_scorer_name, r.away.top_scorer_pts = a_top
                break

def compute_awards(rows: List[MatchupRow]) -> Awards:
    awd = Awards()
    if not rows:
        return awd

    # Cupcake: lowest single-team score
    all_teams = []
    for r in rows:
        all_teams.append(("home", r.home))
        all_teams.append(("away", r.away))
    low = min(all_teams, key=lambda x: x[1].score)
    awd.cupcake_team = low[1].name
    awd.cupcake_score = round(low[1].score, 2)

    # Top score: highest single-team score
    high = max(all_teams, key=lambda x: x[1].score)
    awd.top_team = high[1].name
    awd.top_score = round(high[1].score, 2)

    # Kitty (largest gap loss): find matchup with max margin and record loser/winner
    worst = max(rows, key=lambda r: r.margin)
    if worst.home.score > worst.away.score:
        awd.kitty_winner, awd.kitty_loser = worst.home.name, worst.away.name
    else:
        awd.kitty_winner, awd.kitty_loser = worst.away.name, worst.home.name
    awd.kitty_gap = round(abs(worst.home.score - worst.away.score), 2)

    return awd

# ---------------------------
# Context assembly for DOCX
# ---------------------------

def _fmt_pts(x: Optional[float]) -> Optional[str]:
    return None if x is None else f"{x:.2f}".rstrip("0").rstrip(".")

def build_context(league_id: int, year: int, week: int) -> Dict[str, Any]:
    league = get_league(league_id, year)
    rows = fetch_week_from_espn(league, week)
    # Try to add player tops; it's okay if it fails
    enrich_with_player_tops(league, week, rows)

    ctx: Dict[str, Any] = {}
    ctx["LEAGUE_ID"] = league_id
    ctx["YEAR"] = year
    ctx["WEEK_NUMBER"] = week

    # FIX: support object or dict settings
    league_name = _safe_settings_name(league) or "League"
    ctx["LEAGUE_NAME"] = league_name

    # Per-matchup fields, 1-based up to 7 just in case
    for i, r in enumerate(rows, start=1):
        ctx[f"MATCHUP{i}_HOME"] = r.home.name
        ctx[f"MATCHUP{i}_AWAY"] = r.away.name
        ctx[f"MATCHUP{i}_HS"]   = _fmt_pts(r.home.score)
        ctx[f"MATCHUP{i}_AS"]   = _fmt_pts(r.away.score)

        ctx[f"MATCHUP{i}_HOME_TOP_SCORER"] = r.home.top_scorer_name or ""
        ctx[f"MATCHUP{i}_HOME_TOP_POINTS"] = _fmt_pts(r.home.top_scorer_pts) or ""
        ctx[f"MATCHUP{i}_AWAY_TOP_SCORER"] = r.away.top_scorer_name or ""
        ctx[f"MATCHUP{i}_AWAY_TOP_POINTS"] = _fmt_pts(r.away.top_scorer_pts) or ""

        # Aliases for older templates
        ctx[f"MATCHUP{i}_TOP_SCORER_HOME"] = ctx[f"MATCHUP{i}_HOME_TOP_SCORER"]
        ctx[f"MATCHUP{i}_TOP_SCORER_AWAY"] = ctx[f"MATCHUP{i}_AWAY_TOP_SCORER"]
        ctx[f"MATCHUP{i}_TOP_POINTS_HOME"] = ctx[f"MATCHUP{i}_HOME_TOP_POINTS"]
        ctx[f"MATCHUP{i}_TOP_POINTS_AWAY"] = ctx[f"MATCHUP{i}_AWAY_TOP_POINTS"]

    # Awards
    awd = compute_awards(rows)
    ctx["AWARD_CUPCAKE_TEAM"]    = awd.cupcake_team or ""
    ctx["AWARD_CUPCAKE_SCORE"]   = _fmt_pts(awd.cupcake_score) or ""
    ctx["AWARD_KITTY_LOSER"]     = awd.kitty_loser or ""
    ctx["AWARD_KITTY_WINNER"]    = awd.kitty_winner or ""
    ctx["AWARD_KITTY_GAP"]       = _fmt_pts(awd.kitty_gap) or ""
    ctx["AWARD_TOPSCORE_TEAM"]   = awd.top_team or ""
    ctx["AWARD_TOPSCORE_POINTS"] = _fmt_pts(awd.top_score) or ""

    ctx["CUPCAKE_LINE"] = (f"{ctx['AWARD_CUPCAKE_TEAM']} — {ctx['AWARD_CUPCAKE_SCORE']}"
                           if ctx["AWARD_CUPCAKE_TEAM"] else "—")
    ctx["KITTY_LINE"]    = (f"{ctx['AWARD_KITTY_LOSER']} — {ctx['AWARD_KITTY_GAP']}"
                           if ctx["AWARD_KITTY_LOSER"] else "—")
    ctx["TOPSCORE_LINE"] = (f"{ctx['AWARD_TOPSCORE_TEAM']} — {ctx['AWARD_TOPSCORE_POINTS']}"
                           if ctx["AWARD_TOPSCORE_TEAM"] else "—")

    # Legacy aliases that some templates use
    ctx["CUPCAKE"] = ctx["CUPCAKE_LINE"]
    ctx["KITTY"]   = ctx["KITTY_LINE"]
    ctx["TOPSCORE"]= ctx["TOPSCORE_LINE"]

    return ctx
