# gazette_data.py
# Shared data layer: ESPN fetch + optional OpenAI blurbs + context building.
# Now supports "mascot voice" blurbs using descriptions from team_mascots.py.

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

# ---------- Blurb generation ----------

def _neutral_blurb(home: str, away: str, hs: float, ascore: float) -> str:
    """Fallback / neutral one-liner (used if no API key or style=neutral)."""
    if hs == ascore:
        return f"{home} and {away} finished level, {hs:.1f}-{ascore:.1f}."
    winner, wpts, loser, lpts = (home, hs, away, ascore) if hs >= ascore else (away, ascore, home, hs)
    return f"{winner} edged {loser}, {wpts:.1f}-{lpts:.1f}."

def _mascot_prompt(home: str, away: str, hs: float, ascore: float,
                   home_desc: Optional[str], away_desc: Optional[str], league_name: str) -> str:
    """
    Compose a prompt that uses mascot descriptions as the narrative persona.
    Keep it punchy and family-friendly.
    """
    lines = [
        f"League: {league_name}",
        "Write a punchy recap (<= 28 words), family-friendly.",
        "Tone: energetic, local sports column.",
        "Narration: let the team mascots color the voice (not role-play; just flavor).",
        f"Home team: {home} — mascot description: {home_desc or 'n/a'}",
        f"Away team: {away} — mascot description: {away_desc or 'n/a'}",
        f"Final score: {home} {hs:.1f} – {away} {ascore:.1f}",
        "Avoid emojis. No hashtags. One sentence."
    ]
    return "\n".join(lines)

def _ai_blurb(home: str, away: str, hs: float, ascore: float,
              league_name: str, home_desc: Optional[str], away_desc: Optional[str],
              style: str = "mascot") -> str:
    """
    style = 'mascot' -> use mascot descriptions to influence voice
          = 'neutral' -> straight recap
    Falls back to neutral if no OpenAI client or on error.
    """
    # neutral style or no API key → fallback
    if style != "mascot" or not _OPENAI:
        return _neutral_blurb(home, away, hs, ascore)

    try:
        prompt = _mascot_prompt(home, away, hs, ascore, home_desc, away_desc, league_name)
        resp = _OPENAI.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=72,
        )
        msg = (resp.choices[0].message.content or "").strip()
        return msg or _neutral_blurb(home, away, hs, ascore)
    except Exception:
        return _neutral_blurb(home, away, hs, ascore)

# ---------- ESPN fetch & context ----------

def fetch_week_from_espn(league_id, year, espn_s2, swid, force_week=None):
    from espn_api.football import League
    lg = League(league_id=league_id, year=year, ***REMOVED***
    week = int(force_week) if force_week else getattr(lg, "current_week", None)
    # Prefer last completed week if your lib exposes it; otherwise use week
    games = []
    for m in lg.scoreboard(week=week):
        games.append({
            "home": m.home_team.team_name,
            "away": m.away_team.team_name,
            "hs":   m.home_score,
            "as":   m.away_score,
            # fill the rest as you were (top_home, bust, etc.)
        })
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
    style = (league_cfg.get("blurb_style") or "mascot").lower()  # 'mascot' or 'neutral'
    use_blurbs = league_cfg.get("blurbs", True)

    games_ctx = []
    for g in games:
        # mascot descriptions (free-form text from team_mascots.py)
        home_desc = mascot_for(g.home)
        away_desc = mascot_for(g.away)

        # compose blurb
        if use_blurbs:
            blurb = _ai_blurb(
                home=g.home, away=g.away, hs=g.hs, ascore=g.ascore,
                league_name=league,
                home_desc=home_desc, away_desc=away_desc,
                style=style,
            )
        else:
            blurb = _neutral_blurb(g.home, g.away, g.hs, g.ascore)

        games_ctx.append({
            "home": g.home,
            "away": g.away,
            "hs": int(g.hs) if g.hs.is_integer() else g.hs,
            "as": int(g.ascore) if g.ascore.is_integer() else g.ascore,
            # Keep these as the *descriptions*, so templates can show them directly if desired:
            "home_mascot": home_desc,
            "away_mascot": away_desc,
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
