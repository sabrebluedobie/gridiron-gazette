# gazette_data.py
# Shared data layer: ESPN fetch + optional OpenAI blurbs + context building (with mascots)

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import os

from mascots_util import mascot_for

# ESPN API (pip install espn-api)
try:
    from espn_api.football import League
except Exception:
    League = None  # handled below

# OpenAI (pip install openai >= 1.0)
try:
    from openai import OpenAI
    _OPENAI = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None
except Exception:
    _OPENAI = None

@dataclass
class Game:
    home: str
    away: str
    hs: int
    ascore: int
    blurb: Optional[str] = None

def fetch_week_from_espn(league_id: int, year: int, ***REMOVED***
    """Fetch games for the given/current week from ESPN. Works with public or private (needs cookies)."""
    if League is None:
        raise RuntimeError("espn-api not installed. Run: pip install espn-api")
    league = League(
        league_id=league_id,
        year=year,
        ***REMOVED***
        ***REMOVED***
    )
    wk = week or getattr(league, "current_week", None) or 1
    matchups = league.scoreboard(wk)
    games: List[Game] = []
    for m in matchups:
        home_name = getattr(m.home_team, "team_name", str(getattr(m.home_team, "name", "Home")))
        away_name = getattr(m.away_team, "team_name", str(getattr(m.away_team, "name", "Away")))
        hs = int(round(m.home_score or 0))
        ascore = int(round(m.away_score or 0))
        games.append(Game(home=home_name, away=away_name, hs=hs, ascore=ascore))
    return games

def _ai_blurb(line: str, league_name: str) -> str:
    """Make a short recap line with OpenAI, or gracefully fall back."""
    if not _OPENAI:
        return line
    try:
        prompt = (
            f"League: {league_name}\n"
            f"Write a single punchy recap (<=18 words) in neutral tone.\n"
            f"{line}"
        )
        resp = _OPENAI.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=64,
        )
        txt = (resp.choices[0].message.content or "").strip()
        return txt or line
    except Exception:
        return line

def build_context(league_cfg: Dict[str, Any], games: List[Game]) -> Dict[str, Any]:
    """Return the docxtpl context for rendering."""
    league = league_cfg.get("name", "League")
    week_label = league_cfg.get("week_label") or "This Week"

    games_ctx = []
    for g in games:
        base_line = f"{g.home} {g.hs} vs {g.away} {g.ascore}."
        blurb = _ai_blurb(base_line, league) if league_cfg.get("blurbs", True) else None
        games_ctx.append({
            "home": g.home,
            "away": g.away,
            "hs": g.hs,
            "as": g.ascore,                 # 'as' is fine in Jinja context
            "home_mascot": mascot_for(g.home),
            "away_mascot": mascot_for(g.away),
            "blurb": blurb,
        })

    return {
        "league": league,
        "title": f"{league} — {week_label}",
        "week": week_label,
        "games": games_ctx,
        "sponsor": league_cfg.get("sponsor", {}),
    }
