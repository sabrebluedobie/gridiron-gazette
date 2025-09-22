#!/usr/bin/env python3
"""
gazette_data.py

Provides:
  - espn_cookies(): read ESPN_S2 / SWID from env (adds braces to SWID if missing)
  - espn_get():     requests.get with those cookies
  - load_scoreboard(): pull basic matchup data for a league/week
  - assemble_context(): produce a template-ready context for build_gazette.py

Note: ESPN endpoints are unofficial; if they change, this will fall back safely.
"""
from __future__ import annotations
import os, datetime as dt, requests
from typing import Dict, Any, List

# --------------- ESPN auth helpers -----------------
def espn_cookies() -> dict:
    s2 = os.getenv("ESPN_S2", "").strip()
    swid = os.getenv("SWID", "").strip()
    if not s2 or not swid:
        print(f"[espn] Missing auth cookies: ESPN_S2? {'yes' if s2 else 'no'}; SWID? {'yes' if swid else 'no'}")
        # do not raise — allow caller to fallback
        return {}
    if not (swid.startswith("{") and swid.endswith("}")):
        print("[espn] SWID missing surrounding braces { } — fixing at runtime")
        swid = "{" + swid.strip("{}") + "}"
    return {"espn_s2": s2, "SWID": swid}

def espn_get(url: str, params: dict | None = None, timeout: int = 30) -> requests.Response:
    cookies = espn_cookies()
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    return requests.get(url, params=params or {}, headers=headers, cookies=cookies, timeout=timeout)

# --------------- Minimal data shaping -----------------
def load_scoreboard(league_id: str, year: int, week: int) -> Dict[str, Any]:
    """
    Pull a minimal set of matchup data. If auth or API fails, return a stub.
    """
    base = f"https://fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{league_id}"
    params = {"scoringPeriodId": week, "view": "mMatchupScore"}
    try:
        r = espn_get(base, params=params)
        print(f"[espn] GET {r.url} -> {r.status_code}")
        if r.status_code != 200:
            print(f"[espn] HTTP {r.status_code} fetching scoreboard; falling back.")
            return {"games": []}
        data = r.json()
    except Exception as e:
        print(f"[espn] Exception fetching scoreboard: {e}; falling back.")
        return {"games": []}

    teams = data.get("teams", []) or []
    sched = data.get("schedule", []) or []
    print(f"[espn] teams={len(teams)} schedule={len(sched)} week={week}")

    # id -> friendly name
    id_to_team: Dict[int, Dict[str, Any]] = {}
    for t in teams:
        tid = t.get("id")
        loc = (t.get("location") or "").strip()
        nick = (t.get("nickname") or "").strip()
        nm = (loc + " " + nick).strip() or f"Team {tid}"
        if tid is not None:
            id_to_team[tid] = {"name": nm}

    games: List[Dict[str, Any]] = []
    for m in sched:
        h = (m.get("home") or {})
        a = (m.get("away") or {})
        home_id = h.get("teamId")
        away_id = a.get("teamId")
        if home_id is None or away_id is None:
            continue
        home = id_to_team.get(home_id, {"name": f"Team {home_id}"})
        away = id_to_team.get(away_id, {"name": f"Team {away_id}"})
        hs = h.get("totalPoints", 0)
        as_ = a.get("totalPoints", 0)
        def fmt(x): 
            return f"{x:.1f}" if isinstance(x, (int,float)) else str(x or "0.0")
        games.append({
            "HOME_TEAM_NAME": home["name"],
            "AWAY_TEAM_NAME": away["name"],
            "HOME_SCORE": fmt(hs),
            "AWAY_SCORE": fmt(as_),
            "RECAP": "",
        })

    return {"games": games}


# --------------- Context builder -----------------
def assemble_context(
    league_id: str,
    year: int,
    week: int,
    llm_blurbs: bool,
    blurb_style: str,
) -> Dict[str, Any]:
    """
    Build a template-ready context. If ESPN fetch fails, return a safe stub so build completes.
    """
    # League display name can be provided here if you want a specific league logo mapping
    league_display_name = os.getenv("LEAGUE_DISPLAY_NAME", "Browns SEA/KC")

    sb = load_scoreboard(league_id, year, week)
    games = sb.get("games", [])

    # Pick a "top match" if any games exist
    if games:
        top = max(games, key=lambda g: float(g.get("HOME_SCORE", "0")) + float(g.get("AWAY_SCORE", "0")))
        home = top["HOME_TEAM_NAME"]
        away = top["AWAY_TEAM_NAME"]
    else:
        # minimal stub if no games
        home, away = "Nana's Hawks", "Phoenix Blues"
    
    print(f"[ctx] games={len(games)} chosen-top={home} vs {away}")

    ctx: Dict[str, Any] = {
        "LEAGUE_NAME": league_display_name,
        "LEAGUE_LOGO_NAME": league_display_name,  # for name-based logo resolution
        # You may also explicitly pass file paths (uncomment if desired):
        # "LEAGUE_LOGO_PATH": "logos/team_logos/brownseakc.png",
        # "SPONSOR_LOGO_PATH": "logos/team_logos/gazette_logo.png",

        "WEEK_NUM": week,
        "BLURB_STYLE": blurb_style,
        "GENERATED_AT": dt.datetime.now().isoformat(timespec="seconds"),

        # A single "marquee" block (optional in your template)
        "HOME_TEAM_NAME": home,
        "AWAY_TEAM_NAME": away,

        # Games list used by the template's table/loop
        "GAMES": games,

        # Optional awards; you can compute from full boxscore views if needed
        "AWARDS": [],
    }

    # If you have an LLM step to write blurbs per game/team, this flag can be checked by your renderer
    if llm_blurbs:
        ctx["LLM_NOTE"] = f"Blurbs requested in '{blurb_style}' voice."

    return ctx
