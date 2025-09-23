from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from espn_api.football import League


# -------------------
# Helpers / plumbing
# -------------------

def _env(name: str, alt: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    return v if v is not None and v != "" else (os.getenv(alt) if alt else None)

def _int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default

def _safe_name(x: Any, default: str = "") -> str:
    if x is None:
        return default
    s = str(x).strip()
    return s if s else default


# -------------------
# ESPN objects
# -------------------

def get_league(league_id: int, year: int) -> League:
    """
    Create the League handle using cookies when available.
    SWID must include braces in its value, e.g., {xxxxxxxx-...}
    """
    s2 = _env("ESPN_S2") or _env("S2")
    swid = _env("SWID") or _env("ESPN_SWID")
    return League(league_id=league_id, year=year, espn_s2=s2, swid=swid)


@dataclass
class MatchupRow:
    home_name: str
    away_name: str
    home_score: float
    away_score: float
    home_top_name: str = ""
    home_top_points: float = 0.0
    away_top_name: str = ""
    away_top_points: float = 0.0

    @property
    def gap(self) -> float:
        return abs(self.home_score - self.away_score)

    @property
    def winner(self) -> str:
        return self.home_name if self.home_score >= self.away_score else self.away_name

    @property
    def loser(self) -> str:
        return self.home_name if self.home_score < self.away_score else self.away_name


# --------------------------------
# Extraction from ESPN API objects
# --------------------------------

def _league_display_name(league: League) -> str:
    """
    espn_api changed attributes over time; handle both.
    """
    # 1) Newer versions usually expose .league_name
    name = getattr(league, "league_name", None)
    if name:
        return _safe_name(name, "League")
    # 2) Older pattern: .settings is a Settings object (not a dict)
    settings = getattr(league, "settings", None)
    if settings is not None:
        nm = getattr(settings, "name", None)
        if nm:
            return _safe_name(nm, "League")
    # 3) Fallback
    return "League"


def _top_scorer_from_lineup(lineup: List[Any]) -> Tuple[str, float]:
    """
    lineup elements are PlayerSlot entries; each has .points and .name (or .playerName)
    Only consider starters (slot_position != 'Bench') when possible; if attr missing, just use all.
    """
    top_name, top_pts = "", 0.0
    for slot in lineup or []:
        try:
            # some versions expose .points directly on the slot, others on slot.player
            pts = float(getattr(slot, "points", 0.0) or 0.0)
            nm = (
                getattr(slot, "name", None)
                or getattr(slot, "playerName", None)
                or getattr(getattr(slot, "player", None), "name", None)
            )
            nm = _safe_name(nm, "")
            # Ignore benches when there is a field for it; if not present, we accept all
            bench = getattr(slot, "slot_position", None)
            if bench and str(bench).lower() == "bench":
                continue
            if pts >= top_pts and nm:
                top_name, top_pts = nm, pts
        except Exception:
            continue
    return top_name, float(top_pts)


def _gather_matchups(league: League, week: int) -> List[MatchupRow]:
    """
    Build matchup rows with home/away names, scores, and top scorers from box scores.
    """
    # The league.scoreboard(week) has game containers; league.box_scores(week) has players.
    # We'll map the boxscores by (home, away) team names to enrich with top scorers.
    sb = league.scoreboard(week=week)
    bs = league.box_scores(week=week)

    rows: List[MatchupRow] = []
    # first pass: just scores/names
    for game in sb:
        try:
            home = _safe_name(getattr(game.home_team, "team_name", None))
            away = _safe_name(getattr(game.away_team, "team_name", None))
            hs = float(getattr(game, "home_score", 0.0) or 0.0)
            as_ = float(getattr(game, "away_score", 0.0) or 0.0)
            rows.append(MatchupRow(home_name=home, away_name=away, home_score=hs, away_score=as_))
        except Exception:
            continue

    # second pass: attach top scorers
    for box in bs:
        try:
            hname = _safe_name(getattr(box.home_team, "team_name", None))
            aname = _safe_name(getattr(box.away_team, "team_name", None))
            htop_name, htop_pts = _top_scorer_from_lineup(getattr(box, "home_lineup", []))
            atop_name, atop_pts = _top_scorer_from_lineup(getattr(box, "away_lineup", []))

            # find the corresponding row (by names)
            for r in rows:
                if r.home_name == hname and r.away_name == aname:
                    if htop_name:
                        r.home_top_name, r.home_top_points = htop_name, htop_pts
                    if atop_name:
                        r.away_top_name, r.away_top_points = atop_name, atop_pts
                    break
        except Exception:
            continue

    return rows


def _compute_awards(rows: List[MatchupRow]) -> Dict[str, Any]:
    """
    Cupcake: overall lowest team score
    Kitty: largest losing margin
    Top Score: overall highest team score
    """
    awards: Dict[str, Any] = {}

    if not rows:
        return {
            "CUPCAKE_LINE": "—",
            "KITTY_LINE": "—",
            "TOPSCORE_LINE": "—",
            "AWARD_CUPCAKE_TEAM": "",
            "AWARD_CUPCAKE_SCORE": "",
            "AWARD_KITTY_WINNER": "",
            "AWARD_KITTY_LOSER": "",
            "AWARD_KITTY_GAP": "",
            "AWARD_TOPSCORE_TEAM": "",
            "AWARD_TOPSCORE_POINTS": "",
        }

    # Flatten team scores
    all_teams: List[Tuple[str, float]] = []
    kitty_candidates: List[Tuple[str, str, float]] = []  # winner, loser, gap

    for r in rows:
        all_teams.append((r.home_name, r.home_score))
        all_teams.append((r.away_name, r.away_score))
        winner, loser = r.winner, r.loser
        kitty_candidates.append((winner, loser, r.gap))

    # Cupcake (min score)
    cup_team, cup_pts = min(all_teams, key=lambda x: x[1])

    # Top score (max)
    top_team, top_pts = max(all_teams, key=lambda x: x[1])

    # Kitty (largest gap loss)
    kitty_winner, kitty_loser, kitty_gap = max(kitty_candidates, key=lambda x: x[2])

    awards.update(
        {
            "CUPCAKE_LINE": f"{cup_team} — {cup_pts:.2f}",
            "KITTY_LINE": f"{kitty_loser} fell to {kitty_winner} by {kitty_gap:.2f}",
            "TOPSCORE_LINE": f"{top_team} — {top_pts:.2f}",
            "AWARD_CUPCAKE_TEAM": cup_team,
            "AWARD_CUPCAKE_SCORE": f"{cup_pts:.2f}",
            "AWARD_KITTY_WINNER": kitty_winner,
            "AWARD_KITTY_LOSER": kitty_loser,
            "AWARD_KITTY_GAP": f"{kitty_gap:.2f}",
            "AWARD_TOPSCORE_TEAM": top_team,
            "AWARD_TOPSCORE_POINTS": f"{top_pts:.2f}",
        }
    )
    return awards


# -------------------
# Public entry point
# -------------------

def build_context(league_id: int, year: int, week: int) -> Dict[str, Any]:
    """
    Main context builder consumed by weekly_recap.py.
    Produces:
      - LEAGUE_NAME, YEAR, WEEK_NUMBER
      - MATCHUP{i}_HOME/AWAY/HS/AS plus top-scorer fields
      - Award lines + fields
      - SPONSOR_NAME (optional), so templates can print a sponsor footer
    """
    lid = _int(league_id)
    yr = _int(year)
    wk = _int(week)

    league = get_league(lid, yr)
    league_name = _league_display_name(league)

    # If caller passed week=0, try current period; otherwise honor provided week.
    if wk <= 0:
        wk = getattr(league, "currentMatchupPeriod", 1)

    rows = _gather_matchups(league, wk)

    ctx: Dict[str, Any] = {
        "LEAGUE_ID": lid,
        "YEAR": yr,
        "WEEK_NUMBER": wk,
        "LEAGUE_NAME": league_name,
        # Let the template print a sponsor if configured (defaults to your brand)
        "SPONSOR_NAME": os.getenv("SPONSOR_NAME", "Gridiron Gazette"),
    }

    # Fill matchup slots (template covers up to 7 rows)
    for i, r in enumerate(rows[:7], start=1):
        ctx[f"MATCHUP{i}_HOME"] = r.home_name
        ctx[f"MATCHUP{i}_AWAY"] = r.away_name
        ctx[f"MATCHUP{i}_HS"] = f"{r.home_score:.2f}"
        ctx[f"MATCHUP{i}_AS"] = f"{r.away_score:.2f}"
        ctx[f"MATCHUP{i}_HOME_TOP_SCORER"] = r.home_top_name or ""
        ctx[f"MATCHUP{i}_HOME_TOP_POINTS"] = f"{r.home_top_points:.2f}" if r.home_top_points else ""
        ctx[f"MATCHUP{i}_AWAY_TOP_SCORER"] = r.away_top_name or ""
        ctx[f"MATCHUP{i}_AWAY_TOP_POINTS"] = f"{r.away_top_points:.2f}" if r.away_top_points else ""

    # Awards
    ctx.update(_compute_awards(rows))

    return ctx
