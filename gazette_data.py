#!/usr/bin/env python3
"""
gazette_data.py

Provides:
  - connect_league(league_id, year, espn_s2="", swid="")
  - fetch_week_from_espn(league_id, year, espn_s2="", swid="", week=None) -> list[dict]
  - build_context(cfg: dict, games: list[dict|obj]) -> dict

Design:
  * We normalize every game into a plain dict with keys:
      home, away, hs, as, blurb, top_home, top_away, bust, keyplay, def
  * Robust against objects (e.g., SimpleNamespace) returned by libs:
      use vars(obj) when needed.
  * Awards computed from normalized scores.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import os
import math
import json
import requests


def espn_cookies() -> dict:
    s2 = os.getenv("ESPN_S2", "").strip()
    swid = os.getenv("SWID", "").strip()
    if not s2 or not swid:
        # Masked diagnostics (don’t print values)
        print(f"[espn] Missing auth cookies: ESPN_S2? {'yes' if s2 else 'no'}; SWID? {'yes' if swid else 'no'}")
        raise RuntimeError("ESPN auth cookies not present. Ensure ESPN_S2 and SWID are set in Actions secrets/environment.")
    # SWID must be in braces, e.g. "{ABCD-...-1234}"
    if not (swid.startswith("{") and swid.endswith("}")):
        print("[espn] SWID missing surrounding braces { } — fixing at runtime")
        swid = "{" + swid.strip("{}") + "}"
    return {"espn_s2": s2, "SWID": swid}

def espn_get(url: str, params=None) -> requests.Response:
    ck = espn_cookies()
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    return requests.get(url, params=params or {}, headers=headers, cookies=ck, timeout=30)


# ----- optional mascot helpers (never fail if missing) -----------------------
try:
    from mascots_util import mascot_for  # type: ignore
except Exception:
    def mascot_for(_: str) -> str:
        return ""


# ----- optional ESPN API (we degrade gracefully) -----------------------------
_ESPN_AVAILABLE = True
try:
    from espn_api.football import League  # type: ignore
except Exception:
    _ESPN_AVAILABLE = False
    League = object  # type: ignore


# ----- small utilities -------------------------------------------------------
def _as_dict(x: Any) -> Dict[str, Any]:
    """Return a best-effort plain dict for dict/namespace/object."""
    if isinstance(x, dict):
        return x.copy()
    try:
        return vars(x).copy()  # SimpleNamespace/most objects
    except Exception:
        out: Dict[str, Any] = {}
        for k in dir(x):
            if k.startswith("_"):
                continue
            v = getattr(x, k, None)
            if callable(v):
                continue
            out[k] = v
        return out


def _first(d: Dict[str, Any], *keys: str, default: Any = "") -> Any:
    """First present & non-empty key value in dict d."""
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def _to_score(val: Any) -> Optional[float]:
    """Convert score-like values to float if possible, else None."""
    if val in (None, ""):
        return None
    try:
        return float(val)
    except Exception:
        try:
            # espn sometimes has nested like {'points': 101.2}
            if isinstance(val, dict) and "points" in val:
                return float(val["points"])
        except Exception:
            pass
    return None


def _default_blurb(home: str, away: str, hs: Optional[float], aS: Optional[float]) -> str:
    if hs is not None and aS is not None:
        return f"{home} {hs:.1f} – {away} {aS:.1f}."
    return f"{home} vs {away}."


# ----- ESPN glue -------------------------------------------------------------
def connect_league(league_id: int, year: int, espn_s2: str = "", swid: str = "") -> Any:
    """
    Return an espn_api League object when the package is available.
    Will raise RuntimeError with a helpful message if the library is missing.
    """
    if not _ESPN_AVAILABLE:
        raise RuntimeError("espn-api not installed. Run: pip install espn-api")

    cookies = None
    if espn_s2 and swid:
        cookies = {"swid": swid, "espn_s2": espn_s2}
    # League() accepts cookies=None for public leagues
    return League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid) if cookies \
        else League(league_id=league_id, year=year)


def fetch_week_from_espn(
    league_id: int,
    year: int,
    espn_s2: str = "",
    swid: str = "",
    week: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch a week's scoreboard from ESPN and normalize to a list of dicts:
      {home, away, hs, as, blurb, top_home, top_away, bust, keyplay, def}
    If espn-api is missing, returns an empty list (caller can still render).
    """
    if not _ESPN_AVAILABLE:
        return []

    lg = connect_league(league_id, year, espn_s2, swid)

    # Try both signatures (different espn_api versions exist)
    try:
        raw = lg.scoreboard(week=week) if week else lg.scoreboard()
    except TypeError:
        raw = lg.scoreboard()

    games: List[Dict[str, Any]] = []
    for item in raw:
        d = _as_dict(item)

        # home / away team names: try several shapes
        #   BoxScore.home_team.team_name
        #   d["home_team"]["team_name"]
        #   d["home"]["name"] ...
        def _deep_name(x: Any, *cands: str) -> str:
            if isinstance(x, dict):
                for c in cands:
                    if c in x and isinstance(x[c], str) and x[c]:
                        return x[c]
            try:
                for c in cands:
                    v = getattr(x, c, None)
                    if isinstance(v, str) and v:
                        return v
            except Exception:
                pass
            return ""

        # Pull possible nested structures
        home_obj = _first(d, "home_team", "homeTeam", "home", default={})
        away_obj = _first(d, "away_team", "awayTeam", "away", default={})

        home = _deep_name(home_obj, "team_name", "name") or _first(d, "home_name", default="")
        away = _deep_name(away_obj, "team_name", "name") or _first(d, "away_name", default="")

        # scores live either at top-level or nested under team objects
        hs = _to_score(_first(d, "home_score", "homeScore", "hs",
                              default=_first(_as_dict(home_obj), "score", "points", default=None)))
        aS = _to_score(_first(d, "away_score", "awayScore", "as", "ascore",
                              default=_first(_as_dict(away_obj), "score", "points", default=None)))

        games.append({
            "home": home, "away": away,
            "hs": hs if hs is not None else "",
            "as": aS if aS is not None else "",
            # story fields blank by default (runner may expand with LLM)
            "blurb": "",
            "top_home": "", "top_away": "",
            "bust": "", "keyplay": "", "def": "",
        })

    return games


# ----- Context builder -------------------------------------------------------
def build_context(cfg: Dict[str, Any], games_in: List[Any]) -> Dict[str, Any]:
    """
    Build a single context dict the runner expects.
    Input games can be dicts or objects; we normalize them here.
    """
    # Normalize every game to a dict with canonical keys
    norm_games: List[Dict[str, Any]] = []
    for g in (games_in or []):
        d = _as_dict(g)

        home = _first(d, "home", "home_name", "homeTeam", "home_team", default="")
        away = _first(d, "away", "away_name", "awayTeam", "away_team", default="")

        hs = _to_score(_first(d, "hs", "home_score", "homeScore", "home_points", "homePoints", default=None))
        aS = _to_score(_first(d, "as", "away_score", "awayScore", "away_points", "awayPoints", "ascore", default=None))

        blurb    = _first(d, "blurb", "summary", "story", default="")
        top_home = _first(d, "top_home", "home_top", default="")
        top_away = _first(d, "top_away", "away_top", default="")
        bust     = _first(d, "bust", "biggest_bust", default="")
        keyplay  = _first(d, "keyplay", "key_play", default="")
        dnote    = _first(d, "def", "defense_note", "def_note", default="")

        if not blurb:
            blurb = _default_blurb(home, away, hs, aS)

        norm_games.append({
            "home": home, "away": away,
            "hs": hs if hs is not None else "",
            "as": aS if aS is not None else "",
            "blurb": blurb,
            "top_home": top_home, "top_away": top_away,
            "bust": bust, "keyplay": keyplay, "def": dnote,
        })

    # Compute simple awards (top score / low score / largest gap)
    team_points: List[tuple[str, float]] = []
    match_gaps: List[tuple[str, float]] = []

    for g in norm_games:
        h, a = g["home"], g["away"]
        hs = _to_score(g["hs"])
        aS = _to_score(g["as"])
        if hs is not None:
            team_points.append((h, hs))
        if aS is not None:
            team_points.append((a, aS))
        if hs is not None and aS is not None:
            match_gaps.append((f"{h} vs {a}", abs(hs - aS)))

    top_score = max(team_points, key=lambda x: x[1]) if team_points else ("", 0.0)
    low_score = min(team_points, key=lambda x: x[1]) if team_points else ("", 0.0)
    largest_gap = max(match_gaps, key=lambda x: x[1]) if match_gaps else ("", 0.0)

    # Title & labels
    title = cfg.get("name", "Gridiron Gazette")
    week_num = cfg.get("week_num", cfg.get("week", ""))  # runner may overwrite later
    week_label = cfg.get("week_label", cfg.get("week", f"Week {week_num}" if week_num else ""))
    date_label = cfg.get("date", "")

    # Sponsor (optional)
    sponsor = cfg.get("sponsor", {}) or {}

    # Optional mascot blurbs (if user wants to style by mascot later)
    for g in norm_games:
        if not g.get("home_desc"):
            g["home_desc"] = mascot_for(g["home"])
        if not g.get("away_desc"):
            g["away_desc"] = mascot_for(g["away"])

    ctx: Dict[str, Any] = {
        "title": title,
        "week_num": week_num if isinstance(week_num, int) or (isinstance(week_num, str) and week_num) else "",
        "week": week_label,
        "date": date_label,
        "intro": cfg.get("intro", ""),
        "sponsor": sponsor,
        "games": norm_games,
        "awards": {
            "top_score": {"team": top_score[0], "points": top_score[1]},
            "low_score": {"team": low_score[0], "points": low_score[1]},
            "largest_gap": {"desc": largest_gap[0], "gap": largest_gap[1]},
        },
    }
    return ctx
