# gazette_data.py
# Shared data layer: ESPN fetch + optional OpenAI blurbs + context building (with mascots & awards)

from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
import os
import math

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


def _fmt_pts(x) -> float:
    try:
        return float(x or 0)
    except Exception:
        return 0.0


def _top_scorer(lineup) -> Optional[Tuple[str, float, str]]:
    """Return (name, points, pos) for the top starter in lineup."""
    try:
        starters = [p for p in lineup if getattr(p, "slot_position", "") not in ("BE", "IR")]
        if not starters:
            return None
        top = max(starters, key=lambda p: _fmt_pts(getattr(p, "points", 0)))
        name = getattr(getattr(top, "playerName", None) or top, "name", None) or getattr(top, "name", "Player")
        pts = _fmt_pts(getattr(top, "points", 0))
        pos = getattr(top, "slot_position", "")
        return (str(name), pts, pos)
    except Exception:
        return None


def _biggest_bust(home_lineup, away_lineup) -> Optional[str]:
    """Find starter with the worst (actual - projected) delta across both lineups."""
    worst = None  # (delta, label)
    try:
        cand = []
        for p in (home_lineup or []) + (away_lineup or []):
            if getattr(p, "slot_position", "") in ("BE", "IR"):
                continue
            actual = _fmt_pts(getattr(p, "points", 0))
            proj = _fmt_pts(getattr(p, "projected_points", 0))
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


def _ai_one_liner(text: str, league_name: str) -> str:
    """One punchy line; gracefully falls back to the input text."""
    if not _OPENAI:
        return text
    try:
        prompt = (
            f"League: {league_name}\n"
            f"Write a single, punchy recap (<=18 words), neutral tone.\n"
            f"{text}"
        )
        resp = _OPENAI.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6, max_tokens=64,
        )
        msg = resp.choices[0].message.content or ""
        return msg.strip() or text
    except Exception:
        return text


def fetch_week_from_espn(league_id: int, year: int, ***REMOVED***
    """Use box_scores for richer data. Works with public or private (needs cookies)."""
    if League is None:
        raise RuntimeError("espn-api not installed. Run: pip install espn-api")

    league = League(
        league_id=league_id,
        year=year,
        ***REMOVED***
        ***REMOVED***
    )
    wk = week or getattr(league, "current_week", None) or 1
    boxes = league.box_scores(wk)

    games: List[Game] = []
    for b in boxes:
        # Team names
        home_name = getattr(b.home_team, "team_name", str(getattr(b.home_team, "name", "Home")))
        away_name = getattr(b.away_team, "team_name", str(getattr(b.away_team, "name", "Away")))

        # Team scores
        hs = _fmt_pts(getattr(b, "home_score", 0))
        ascore = _fmt_pts(getattr(b, "away_score", 0))

        # Starters lists
        home_lineup = getattr(b, "home_lineup", []) or []
        away_lineup = getattr(b, "away_lineup", []) or []

        # Top scorer per side
        htop = _top_scorer(home_lineup)
        atop = _top_scorer(away_lineup)
        home_top = f"{htop[0]} {htop[1]:.1f} pts ({htop[2]})" if htop else None
        away_top = f"{atop[0]} {atop[1]:.1f} pts ({atop[2]})" if atop else None

        # Bust across both
        bust = _biggest_bust(home_lineup, away_lineup)

        games.append(Game(
            home=home_name, away=away_name, hs=hs, ascore=ascore,
            home_top=home_top, away_top=away_top, biggest_bust=bust
        ))

    return games


def _compute_awards(games: List[Game]) -> Dict[str, Any]:
    """Weekly awards derived from team totals."""
    if not games:
        return {}

    by_team = []
    for g in games:
        by_team.append((f"{g.home}", g.hs))
        by_team.append((f"{g.away}", g.ascore))

    top_score = max(by_team, key=lambda x: x[1])
    low_score = min(by_team, key=lambda x: x[1])

    # Largest margin game
    margins = [ (abs(g.hs - g.ascore), f"{g.home} {g.hs:.1f} – {g.away} {g.ascore:.1f}") for g in games ]
    largest_gap = max(margins, key=lambda x: x[0])

    return {
        "top_score": {"team": top_score[0], "points": f"{top_score[1]:.1f}"},
        "low_score": {"team": low_score[0], "points": f"{low_score[1]:.1f}"},
        "largest_gap": {"desc": largest_gap[1], "gap": f"{largest_gap[0]:.1f}"},
    }


def build_context(league_cfg: Dict[str, Any], games: List[Game]) -> Dict[str, Any]:
    """Return the docxtpl context for rendering (now includes stats + awards)."""
    league = league_cfg.get("name", "League")
    week_label = league_cfg.get("week_label") or "This Week"

    games_ctx = []
    for g in games:
        line = f"{g.home} {g.hs:.1f} vs {g.away} {g.ascore:.1f}."
        blurb = _ai_one_liner(line, league) if league_cfg.get("blurbs", True) else None

        games_ctx.append({
            "home": g.home,
            "away": g.away,
            "hs": g.hs if g.hs % 1 else int(g.hs),
            "as": g.ascore if g.ascore % 1 else int(g.ascore),
            "home_mascot": mascot_for(g.home),
            "away_mascot": mascot_for(g.away),
            "home_top": g.home_top,
            "away_top": g.away_top,
            "biggest_bust": g.biggest_bust,
            "key_play": g.key_play,
            "defense_note": g.defense_note,
            "blurb": blurb,
        })

    awards = _compute_awards(games)

    return {
        "league": league,
        "title": f"{league} — {week_label}",
        "week": week_label,
        "games": games_ctx,
        "awards": awards,
        "sponsor": league_cfg.get("sponsor", {}),
    }

