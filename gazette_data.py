#!/usr/bin/env python3
"""
gazette_data.py — resilient data assembly for the Gazette

- Tries multiple ESPN endpoints with cookies; falls back to espn_api; then to sample data.
- Returns a context dict containing GAMES and high-level awards/metadata.
- Can optionally generate short blurbs (fallback); primary Sabre blurbs are generated in weekly_recap via storymaker.
"""

from __future__ import annotations
import os
import datetime as dt
import json
from pathlib import Path
from typing import Dict, Any, List
from urllib.parse import unquote

import requests


def _get_credentials() -> tuple[str, str, str]:
    espn_s2 = (os.getenv("ESPN_S2") or os.getenv("S2") or "").strip()
    swid = (os.getenv("ESPN_SWID") or os.getenv("SWID") or "").strip()
    league_id = (os.getenv("LEAGUE_ID") or "").strip()

    if espn_s2 and swid:
        # URL decode S2 if pasted encoded
        if "%" in espn_s2:
            espn_s2 = unquote(espn_s2)
        # ensure SWID has braces
        if not (swid.startswith("{") and swid.endswith("}")):
            swid = "{" + swid.strip("{}") + "}"
    return espn_s2, swid, league_id


def _basic_recap(home: str, away: str, hs: float, as_: float) -> str:
    winner, loser = (home, away) if hs >= as_ else (away, home)
    margin = abs(hs - as_)
    if margin < 5:
        return f"Nail-biter! {winner} edges {loser} {hs:.1f}-{as_:.1f}."
    if margin > 30:
        return f"Blowout! {winner} over {loser} {hs:.1f}-{as_:.1f}."
    return f"Solid win for {winner} over {loser}, {hs:.1f}-{as_:.1f}."


def _process_espn_json(data: Dict[str, Any]) -> Dict[str, Any]:
    teams = data.get("teams", [])
    schedule = data.get("schedule", [])

    # Build team lookup
    lookup = {}
    for t in teams:
        tid = t.get("id")
        loc = (t.get("location") or "").strip()
        nick = (t.get("nickname") or "").strip()
        name = f"{loc} {nick}".strip() if (loc or nick) else f"Team {tid}"
        lookup[tid] = name

    games: List[Dict[str, Any]] = []
    for m in schedule:
        hd, ad = m.get("home", {}), m.get("away", {})
        hid, aid = hd.get("teamId"), ad.get("teamId")
        if hid is None or aid is None:
            continue
        hname = lookup.get(hid, f"Team {hid}")
        aname = lookup.get(aid, f"Team {aid}")
        hs = float(hd.get("totalPoints", 0) or 0)
        as_ = float(ad.get("totalPoints", 0) or 0)
        games.append({
            "HOME_TEAM_NAME": hname,
            "AWAY_TEAM_NAME": aname,
            "HOME_SCORE": f"{hs:.1f}",
            "AWAY_SCORE": f"{as_:.1f}",
            "RECAP": _basic_recap(hname, aname, hs, as_),
        })
    return {"games": games}


def _try_http(league_id: str, year: int, week: int) -> Dict[str, Any]:
    s2, swid, _ = _get_credentials()
    if not s2 or not swid:
        return {}

    urls = [
        f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{league_id}",
        f"https://fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{league_id}",
    ]
    cookies_variants = [
        {"espn_s2": s2, "SWID": swid},
        {"ESPN_S2": s2, "SWID": swid},
        {"espn_s2": s2, "swid": swid},
    ]
    headers_variants = [
        {"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Referer": "https://fantasy.espn.com/"},
        {"User-Agent": "ESPN Fantasy App", "Accept": "application/json"},
    ]
    params = {"scoringPeriodId": week, "view": "mMatchupScore"}

    for url in urls:
        for ck in cookies_variants:
            for hd in headers_variants:
                try:
                    r = requests.get(url, params=params, cookies=ck, headers=hd, timeout=20)
                    if r.status_code == 200 and "application/json" in r.headers.get("content-type", ""):
                        return _process_espn_json(r.json())
                except Exception:
                    continue
    return {}


def _try_espn_api(league_id: str, year: int, week: int) -> Dict[str, Any]:
    try:
        from espn_api.football import League  # type: ignore
    except Exception:
        return {}

    s2, swid, _ = _get_credentials()
    if not s2 or not swid:
        return {}

    try:
        league = League(league_id=int(league_id), year=year, espn_s2=s2, swid=swid)
        board = league.scoreboard(week=week)
        games: List[Dict[str, Any]] = []
        for m in board:
            hname = getattr(m.home_team, "team_name", "Home")
            aname = getattr(m.away_team, "team_name", "Away")
            hs = float(getattr(m, "home_score", 0) or 0)
            as_ = float(getattr(m, "away_score", 0) or 0)
            games.append({
                "HOME_TEAM_NAME": hname,
                "AWAY_TEAM_NAME": aname,
                "HOME_SCORE": f"{hs:.1f}",
                "AWAY_SCORE": f"{as_:.1f}",
                "RECAP": _basic_recap(hname, aname, hs, as_),
            })
        return {"games": games}
    except Exception:
        return {}


def _sample_data() -> Dict[str, Any]:
    teams = [
        "Annie1235 slayy",
        "Phoenix Blues",
        "Nana's Hawks",
        "Jimmy Birds",
        "Kansas City Pumas",
        "Under the InfluWENTZ",
        "DEM BOY’S! 🏆🏆🏆🏆",
        "Avondale Welders",
        "THE 💀REBELS💀",
        "The Champ Big Daddy",
    ]
    import random
    random.seed(42)
    games: List[Dict[str, Any]] = []
    for i in range(0, len(teams), 2):
        if i + 1 >= len(teams):
            break
        home, away = teams[i], teams[i+1]
        hs = round(random.uniform(85, 145), 1)
        as_ = round(random.uniform(85, 145), 1)
        games.append({
            "HOME_TEAM_NAME": home,
            "AWAY_TEAM_NAME": away,
            "HOME_SCORE": f"{hs:.1f}",
            "AWAY_SCORE": f"{as_:.1f}",
            "RECAP": _basic_recap(home, away, hs, as_),
            "TOP_HOME": f"{home} RB — 25.4 pts",
            "TOP_AWAY": f"{away} WR — 18.2 pts",
            "BUST": f"{random.choice([home, away])} QB — 3.1 pts",
            "KEY_PLAY": "Long TD pass in Q4",
            "DEF_NOTE": "Defense held strong",
        })
    return {"games": games}


def assemble_context(league_id: str, year: int, week: int, llm_blurbs: bool, blurb_style: str) -> Dict[str, Any]:
    """
    Builds the context dict expected by weekly_recap.
    """
    # 1) Try ESPN HTTP
    data = _try_http(league_id, year, week)
    if not data.get("games"):
        # 2) Try espn_api
        data = _try_espn_api(league_id, year, week)
    if not data.get("games"):
        # 3) Sample fallback
        data = _sample_data()

    games = data.get("games", [])
    scores = []
    for g in games:
        try:
            scores.extend([float(g.get("HOME_SCORE", "0")), float(g.get("AWAY_SCORE", "0"))])
        except Exception:
            pass

    top_score = max(scores) if scores else 0.0
    low_score = min(scores) if scores else 0.0
    top_team = ""
    low_team = ""
    for g in games:
        if float(g.get("HOME_SCORE", "0")) == top_score:
            top_team = g.get("HOME_TEAM_NAME", top_team)
        if float(g.get("AWAY_SCORE", "0")) == top_score:
            top_team = g.get("AWAY_TEAM_NAME", top_team)
        if float(g.get("HOME_SCORE", "0")) == low_score:
            low_team = g.get("HOME_TEAM_NAME", low_team)
        if float(g.get("AWAY_SCORE", "0")) == low_score:
            low_team = g.get("AWAY_TEAM_NAME", low_team)

    league_name = os.getenv("LEAGUE_DISPLAY_NAME") or "Browns SEA/KC"

    ctx: Dict[str, Any] = {
        "LEAGUE_NAME": league_name,
        "LEAGUE_LOGO_NAME": league_name,
        "WEEK_NUM": week,
        "WEEK_NUMBER": week,
        "YEAR": year,
        "GENERATED_AT": dt.datetime.now().isoformat(timespec="seconds"),
        "WEEKLY_INTRO": f"Week {week} delivered some spicy swings and stat lines around the league.",
        "title": f"Week {week} Gridiron Gazette — {league_name}",

        "AWARD_TOP_TEAM": top_team or "Top Scorer",
        "AWARD_TOP_NOTE": f"{top_score:.1f} points" if top_score else "",
        "AWARD_CUPCAKE_TEAM": low_team or "Low Scorer",
        "AWARD_CUPCAKE_NOTE": f"{low_score:.1f} points" if low_score else "",
        "AWARD_KITTY_TEAM": "Closest Finish",
        "AWARD_KITTY_NOTE": "Decided by a whisker",

        "GAMES": games,
        "TOTAL_GAMES": len(games),
        "BLURB_STYLE": blurb_style,
        "LLM_ENABLED": bool(llm_blurbs),
    }

    # Also expose simple MATCHUPn_* for older templates (not strictly needed if we map later)
    for i in range(10):
        if i < len(games):
            g = games[i]
            ctx[f"MATCHUP{i+1}_HOME"] = g.get("HOME_TEAM_NAME", "")
            ctx[f"MATCHUP{i+1}_AWAY"] = g.get("AWAY_TEAM_NAME", "")
            ctx[f"MATCHUP{i+1}_HS"] = g.get("HOME_SCORE", "")
            ctx[f"MATCHUP{i+1}_AS"] = g.get("AWAY_SCORE", "")
            ctx[f"MATCHUP{i+1}_BLURB"] = g.get("RECAP", "")
        else:
            ctx[f"MATCHUP{i+1}_HOME"] = ""
            ctx[f"MATCHUP{i+1}_AWAY"] = ""
            ctx[f"MATCHUP{i+1}_HS"] = ""
            ctx[f"MATCHUP{i+1}_AS"] = ""
            ctx[f"MATCHUP{i+1}_BLURB"] = ""

    return ctx
