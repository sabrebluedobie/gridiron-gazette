# gazette_data.py
# Shared data layer: ESPN fetch + optional OpenAI blurbs + context building.

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
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
    hs: float
    ascore: float
    home_top: Optional[str] = None
    away_top: Optional[str] = None
    biggest_bust: Optional[str] = None
    key_play: Optional[str] = None
    defense_note: Optional[str] = None
    blurb: Optional[str] = None


def _fnum(x) -> float:
    try:
        return float(x or 0)
    except Exception:
        return 0.0

def _top_scorer(lineup) -> Optional[Tuple[str, float, str]]:
    """Return (name, points, pos) for the top starter."""
    try:
        starters = [p for p in (lineup or []) if getattr(p, "slot_position", "") not in ("BE", "IR")]
        if not starters:
            return None
        top = max(starters, key=lambda p: _fnum(getattr(p, "points", 0)))
        name = getattr(getattr(top, "playerName", None) or top, "name", None) or getattr(top, "name", "Player")
        pts = _fnum(getattr(top, "points", 0))
        pos = getattr(top, "slot_position", "") or getattr(top, "position", "")
        return (str(name), pts, pos)
    except Exception:
        return None

def _biggest_bust(home_lineup, away_lineup) -> Optional[str]:
    worst = None
    cand = []
    try:
        for p in (home_lineup or []) + (away_lineup or []):
            if getattr(p, "slot_position", "") in ("BE", "IR"):
                continue
            actual = _fnum(getattr(p, "points", 0))
            proj = _fnum(getattr(p, "projected_points", 0))
            delta = actual - proj
            name = getattr(getattr(p, "playerName", None) or p, "name", None) or getattr(p, "name", "Player")
            team = getattr(p, "proTeam", "") or ""
            pos = getattr(p, "position", "") or getattr(p, "slot_position", "")
            cand.append((delta, f"{name} ({pos} {team}) {actual:.1f} vs {proj:.1f} proj"))
        if not cand:
            return None
        worst = min(cand, key=lambda x: x[0])
        return worst[1]
    except Exception:
        return None

def _ai_line(text: str, league_name: str) -> str:
    if not _OPENAI:
        return text
    try:
        resp = _OPENAI.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user",
                       "content": f"League: {league_name}\nWrite a single, punchy recap (<=18 words), neutral tone.\n{text}"}],
            temperature=0.6, max_tokens=64,
        )
        msg = (resp.choices[0].message.content or "").strip()
        return msg or text
    except Exception:
        return text

def fetch_week_from_espn(league_id: int, year: int, ***REMOVED***
    """Richer fetch using box_scores (works with public; for private pass cookies)."""
    if League is None:
        raise RuntimeError("espn-api not installed. Run: pip install espn-api")
    league = League(league_id=league_id, year=year, ***REMOVED***
    wk = week or getattr(league, "current_week", None) or 1
    boxes = league.box_scores(wk)
    games: List[Game] = []
    for b in boxes:
        home_name = getattr(b.home_team, "team_name", str(getattr(b.home_team, "name", "Home")))
        away_name = getattr(b.away_team, "team_name", str(getattr(b.away_team, "name", "Away")))
        hs = _fnum(getattr(b, "home_score", 0))
        ascore = _fnum(getattr(b, "away_score", 0))
        htop = _top_scorer(getattr(b, "home_lineup", []) or [])
        atop = _top_scorer(getattr(b, "away_lineup", []) or [])
        home_top = f"{htop[0]} {htop[1]:.1f} pts ({htop[2]})" if htop else None
        away_top = f"{atop[0]} {atop[1]:.1f} pts ({atop[2]})" if atop else None
        bust = _biggest_bust(getattr(b, "home_lineup", []) or [], getattr(b, "away_lineup", []) or [])
        games.append(Game(home=home_name, away=away_name, hs=hs, ascore=ascore,
                          home_top=home_top, away_top=away_top, biggest_bust=bust))
    return games

def _awards(games: List[Game]) -> Dict[str, Any]:
    if not games:
        return {}
    by_team = []
    for g in games:
        by_team.append((g.home, g.hs))
        by_team.append((g.away, g.ascore))
    top = max(by_team, key=lambda x: x[1])
    low = min(by_team, key=lambda x: x[1])
    margins = [(abs(g.hs - g.ascore), f"{g.home} {g.hs:.1f} – {g.away} {g.ascore:.1f}") for g in games]
    gap = max(margins, key=lambda x: x[0])
    return {
        "top_score": {"team": top[0], "points": f"{top[1]:.1f}"},
        "low_score": {"team": low[0], "points": f"{low[1]:.1f}"},
        "largest_gap": {"desc": gap[1], "gap": f"{gap[0]:.1f}"},
    }

def build_context(league_cfg: Dict[str, Any], games: List[Game]) -> Dict[str, Any]:
    league = league_cfg.get("name", "League")
    week_label = league_cfg.get("week_label") or "This Week"
    games_ctx = []
    for g in games:
        base_line = f"{g.home} {g.hs:.1f} vs {g.away} {g.ascore:.1f}."
        blurb = _ai_line(base_line, league) if league_cfg.get("blurbs", True) else None
        games_ctx.append({
            "home": g.home,
            "away": g.away,
            "hs": int(g.hs) if g.hs.is_integer() else g.hs,
            "as": int(g.ascore) if g.ascore.is_integer() else g.ascore,
            "home_mascot": mascot_for(g.home),
            "away_mascot": mascot_for(g.away),
            "home_top": g.home_top,
            "away_top": g.away_top,
            "biggest_bust": g.biggest_bust,
            "key_play": g.key_play,
            "defense_note": g.defense_note,
            "blurb": blurb,
        })
    return {
        "league": league,
        "title": f"{league} — {week_label}",
        "week": week_label,
        "games": games_ctx,
        "awards": _awards(games),
        "sponsor": league_cfg.get("sponsor", {}),
    }
