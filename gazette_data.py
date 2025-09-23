#!/usr/bin/env python3
"""
gazette_data.py — ESPN fetch & context assembly for Gridiron Gazette

Goals:
- Always return GAME entries with names + numeric scores as STRINGS for DocxTPL.
- Work with either env name pair: (ESPN_S2 or S2) and (SWID or ESPN_SWID).
- Be resilient if ESPN hides starters: scoreboard still gives team scores.
- Provide optional player-derived Spotlight when starters are visible.
- Precompute Weekly Awards (Cupcake, Kitty, Top Score).

Exports:
- fetch_week_from_espn(league, year, week) -> dict
- assemble_context(league_id:str, year:int, week:int, llm_blurbs:bool=False, blurb_style:str="sabre") -> dict
- build_context = assemble_context  (back-compat)
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import os
import logging

log = logging.getLogger("gazette_data")
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

try:
    from espn_api.football import League
except Exception:  # package not installed or import error
    League = None  # type: ignore


# ------------------- helpers -------------------

def _env(name: str) -> Optional[str]:
    v = os.getenv(name)
    return v.strip() if isinstance(v, str) and v.strip() else None

def _coerce_str(x) -> str:
    """Return a clean string for docxtpl."""
    try:
        if x is None:
            return ""
        if isinstance(x, float):
            s = f"{x:.2f}".rstrip("0").rstrip(".")
            return s
        return str(x)
    except Exception:
        return str(x)

def _float_or_none(x) -> Optional[float]:
    try:
        return float(x)
    except Exception:
        return None

def _team_display_name(t: Any) -> str:
    """
    Prefer 'team_name'; fall back to 'location'/'name' or first owner if needed.
    Avoid properties that changed across espn_api versions (e.g., .owner vs .owners).
    """
    for attr in ("team_name", "location", "name"):
        if hasattr(t, attr):
            v = getattr(t, attr)
            if isinstance(v, str) and v.strip():
                return v
    if hasattr(t, "owners") and t.owners:
        return str(t.owners[0])
    return "Team"

def _make_league(league_id: int, year: int) -> Optional[Any]:
    """Create League with tolerant env var names for cookies."""
    if League is None:
        log.error("espn_api not available; install espn-api")
        return None
    s2 = _env("ESPN_S2") or _env("S2")
    swid = _env("SWID") or _env("ESPN_SWID")
    try:
        L = League(league_id=league_id, year=year, espn_s2=s2, swid=swid)
        log.info("League object created successfully")
        return L
    except Exception as e:
        log.error("League creation failed: %s", e)
        return None

# ------------------- core fetch -------------------

def fetch_week_from_espn(league: Any, year: int, week: int) -> Dict[str, Any]:
    """
    Pull league name + scoreboard for the week.
    Always returns dict with keys: LEAGUE_NAME, GAMES (list of dicts)
    Each game dict contains stringified HOME_SCORE/AWAY_SCORE for docxtpl.
    Spotlight placeholders are included but may be filled later by builder.
    """
    out: Dict[str, Any] = {"LEAGUE_NAME": "", "GAMES": []}
    if not league:
        log.warning("No League object; returning empty context shell")
        return out

    # league name
    lname = ""
    try:
        if getattr(league, "settings", None) and getattr(league.settings, "name", None):
            lname = league.settings.name
        elif getattr(league, "league_name", None):
            lname = league.league_name
    except Exception:
        pass
    out["LEAGUE_NAME"] = lname or os.getenv("LEAGUE_DISPLAY_NAME") or "League"

    # scoreboard
    try:
        log.info("Fetching scoreboard for week %s", week)
        board = league.scoreboard(week)
        log.info("Scoreboard fetched: %d matchups", len(board) if board else 0)
        games: List[Dict[str, Any]] = []
        for m in board:
            ht = getattr(m, "home_team", None)
            at = getattr(m, "away_team", None)
            hs = getattr(m, "home_score", 0.0)
            as_ = getattr(m, "away_score", 0.0)
            g = {
                "HOME_TEAM_NAME": _team_display_name(ht),
                "AWAY_TEAM_NAME": _team_display_name(at),
                "HOME_SCORE": _coerce_str(hs),
                "AWAY_SCORE": _coerce_str(as_),
                # Spotlight placeholders (builder may fill from starters or fallback)
                "TOP_HOME": "", "TOP_AWAY": "", "BUST": "", "KEYPLAY": "", "DEF": "",
            }
            games.append(g)
        out["GAMES"] = games
        log.info("Successfully extracted data for %d games", len(games))
    except Exception as e:
        log.error("Failed to read scoreboard: %s", e)

    return out

# ------------------- awards (from team scores) -------------------

def _compute_awards(games: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Compute three weekly awards from team scores:
    - CUPCAKE (lowest single-team score)
    - KITTY (largest losing margin)
    - TOPSCORE (highest single-team score)
    Returns dict with friendly strings suitable for docx placeholders.
    """
    lows: List[Tuple[str, float]] = []
    highs: List[Tuple[str, float]] = []
    margins: List[Tuple[str, str, float]] = []

    for g in games:
        home, away = g.get("HOME_TEAM_NAME","Home"), g.get("AWAY_TEAM_NAME","Away")
        hs = _float_or_none(g.get("HOME_SCORE")); as_ = _float_or_none(g.get("AWAY_SCORE"))
        if hs is not None:
            lows.append((home, hs)); highs.append((home, hs))
        if as_ is not None:
            lows.append((away, as_)); highs.append((away, as_))
        if hs is not None and as_ is not None:
            if hs >= as_:
                margins.append((away, home, hs - as_))  # away lost by (hs-as)
            else:
                margins.append((home, away, as_ - hs))  # home lost by (as-hs)

    awards: Dict[str, str] = {}

    if lows:
        loser, score = min(lows, key=lambda t: t[1])
        s = f"{score:.2f}".rstrip("0").rstrip(".")
        awards["CUPCAKE"] = f"{loser} — {s}"
    else:
        awards["CUPCAKE"] = "—"

    if margins:
        losing_team, winning_team, gap = max(margins, key=lambda t: t[2])
        s = f"{gap:.2f}".rstrip("0").rstrip(".")
        awards["KITTY"] = f"{losing_team} to {winning_team} — {s}"
    else:
        awards["KITTY"] = "—"

    if highs:
        top_team, top = max(highs, key=lambda t: t[1])
        s = f"{top:.2f}".rstrip("0").rstrip(".")
        awards["TOPSCORE"] = f"{top_team} — {s}"
    else:
        awards["TOPSCORE"] = "—"

    return awards

# ------------------- assemble_context (public) -------------------

def assemble_context(league_id: str, year: int, week: int,
                     llm_blurbs: bool = False, blurb_style: str = "sabre") -> Dict[str, Any]:
    """
    Main context for the template. Returns:
      LEAGUE_NAME, WEEK_NUMBER, WEEKLY_INTRO, GAMES[...],
      plus CUPCAKE / KITTY / TOPSCORE strings for your awards section.
    """
    ctx: Dict[str, Any] = {
        "LEAGUE_NAME": os.getenv("LEAGUE_DISPLAY_NAME") or "League",
        "WEEK_NUMBER": week,
        "WEEKLY_INTRO": f"Week {week} delivered thrilling fantasy performances across head-to-head battles.",
        "GAMES": [],
        "CUPCAKE": "—",
        "KITTY": "—",
        "TOPSCORE": "—",
    }

    # Create the League
    try:
        lid = int(league_id) if isinstance(league_id, str) else int(league_id)
    except Exception:
        lid = int(str(league_id).strip())

    L = _make_league(lid, year)
    live = fetch_week_from_espn(L, year, week)

    if live.get("LEAGUE_NAME"):
        ctx["LEAGUE_NAME"] = live["LEAGUE_NAME"]
    if live.get("GAMES"):
        ctx["GAMES"] = live["GAMES"]

    # Awards from the scores we have (works even if starters hidden)
    if ctx["GAMES"]:
        awards = _compute_awards(ctx["GAMES"])
        ctx.update(awards)
    else:
        log.warning("No games found to compute awards")

    return ctx

# Back-compat alias
build_context = assemble_context
