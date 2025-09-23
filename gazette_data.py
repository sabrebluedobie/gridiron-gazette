#!/usr/bin/env python3
"""
gazette_data.py — fetches ESPN week data and assembles context for DocxTPL.

Exports:
- fetch_week_from_espn(league, year, week)
- assemble_context(league_id:str, year:int, week:int, llm_blurbs:bool=False, blurb_style:str="sabre")
- build_context = assemble_context  (back-compat)

This file is tolerant: it renders even if ESPN hides starters; it still emits
HOME_SCORE / AWAY_SCORE so your tables and Spotlight fallbacks work.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import os

try:
    from espn_api.football import League
except Exception:
    League = None  # handled below


def _env(name: str) -> Optional[str]:
    v = os.getenv(name)
    return v.strip() if isinstance(v, str) and v.strip() else None


def _strf(x) -> str:
    try:
        if x is None:
            return ""
        if isinstance(x, float):
            return f"{x:.2f}".rstrip("0").rstrip(".")
        return str(x)
    except Exception:
        return str(x)


def _safe_team_name(t: Any) -> str:
    # prefer proper team name/location; fall back to owners if needed
    for attr in ("team_name", "team", "location", "name"):
        if hasattr(t, attr):
            v = getattr(t, attr)
            if isinstance(v, str) and v.strip():
                return v
    if hasattr(t, "owners") and t.owners:
        return str(t.owners[0])
    return "Team"


def _make_league(league_id: int, year: int) -> Optional[Any]:
    if League is None:
        return None
    s2 = _env("ESPN_S2") or _env("S2")  # tolerate both names
    swid = _env("SWID") or _env("ESPN_SWID")
    try:
        return League(league_id=league_id, year=year, espn_s2=s2, swid=swid)
    except Exception:
        return None


def fetch_week_from_espn(league: Any, year: int, week: int) -> Dict[str, Any]:
    """Return dict with LEAGUE_NAME and GAMES[{HOME/ AWAY names & scores}] from scoreboard."""
    out: Dict[str, Any] = {"LEAGUE_NAME": "", "GAMES": []}
    if not league:
        return out

    # league name (try settings.name, then league_name)
    lname = ""
    try:
        if getattr(league, "settings", None) and getattr(league.settings, "name", None):
            lname = league.settings.name
        elif getattr(league, "league_name", None):
            lname = league.league_name
    except Exception:
        pass
    out["LEAGUE_NAME"] = lname or os.getenv("LEAGUE_DISPLAY_NAME") or "League"

    try:
        board = league.scoreboard(week)
        games: List[Dict[str, Any]] = []
        for m in board:
            ht = getattr(m, "home_team", None)
            at = getattr(m, "away_team", None)
            hs = getattr(m, "home_score", 0.0)
            as_ = getattr(m, "away_score", 0.0)
            games.append({
                "HOME_TEAM_NAME": _safe_team_name(ht),
                "AWAY_TEAM_NAME": _safe_team_name(at),
                "HOME_SCORE": _strf(hs),
                "AWAY_SCORE": _strf(as_),
                "TOP_HOME": "", "TOP_AWAY": "", "BUST": "", "KEYPLAY": "", "DEF": "",
            })
        out["GAMES"] = games
    except Exception:
        pass

    return out


def assemble_context(league_id: str, year: int, week: int,
                     llm_blurbs: bool = False, blurb_style: str = "sabre") -> Dict[str, Any]:
    """Master context for DocxTPL; safe even if ESPN hides players."""
    ctx: Dict[str, Any] = {
        "LEAGUE_NAME": os.getenv("LEAGUE_DISPLAY_NAME") or "League",
        "WEEK_NUMBER": week,
        "WEEKLY_INTRO": f"Week {week} delivered thrilling fantasy performances across head-to-head battles.",
        "GAMES": [],
    }
    try:
        league_int = int(league_id)
    except Exception:
        league_int = int(str(league_id).strip())

    L = _make_league(league_int, year)
    live = fetch_week_from_espn(L, year, week)
    if live.get("LEAGUE_NAME"):
        ctx["LEAGUE_NAME"] = live["LEAGUE_NAME"]
    if live.get("GAMES"):
        ctx["GAMES"] = live["GAMES"]
    return ctx


# back-compat alias
build_context = assemble_context
