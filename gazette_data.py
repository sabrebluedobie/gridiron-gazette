# gazette_data.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

# Only for type-checkers; avoids Pylance complaining when espn_api isn't importable in the editor
if TYPE_CHECKING:
    from espn_api.football import League  # type: ignore


# ---- Optional mascot helpers (do not fail if not present) ----
try:
    from mascots_util import mascot_for as _mascot_for  # returns description string for team name
except Exception:
    def _mascot_for(_: str) -> str:
        return ""


# ---------------- ESPN helpers ----------------

def _import_league():
    """Import League at runtime to avoid editor/venv hiccups."""
    try:
        from espn_api.football import League  # type: ignore
        return League
    except Exception as e:
        raise RuntimeError(
            "espn-api not installed or import failed. Install with: pip install espn-api"
        ) from e


def connect_league(league_id: int, year: int, espn_s2: str = "", swid: str = "") -> "League":
    """
    Create a League, adding cookies only if provided (needed for private leagues).
    String return annotation keeps Pylance happy if the lib isn't resolvable.
    """
    League = _import_league()
    if espn_s2 and swid:
        return League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
    return League(league_id=league_id, year=year)


def _latest_completed_week(lg: "League") -> int:
    """
    Heuristic: use (current_week - 1) if available; fall back to 1.
    """
    try:
        cw = getattr(lg, "current_week", None)
        if isinstance(cw, int) and cw and cw > 1:
            return cw - 1
    except Exception:
        pass
    return 1


def _name_of(team_obj: Any) -> str:
    """
    Robustly extract a printable team name from ESPN team objects.
    """
    if team_obj is None:
        return ""
    for attr in ("team_name", "teamName", "name"):
        val = getattr(team_obj, attr, None)
        if isinstance(val, str) and val.strip():
            return val
    # Sometimes repr is decent
    s = str(team_obj)
    return s if s != "None" else ""


def _max_player(lineup: Any) -> Optional[Tuple[str, float]]:
    """
    From a lineup iterable, return (player_name, points) for the highest scorer.
    """
    best = None
    try:
        for p in (lineup or []):
            name = getattr(p, "name", None) or getattr(p, "playerName", None) or ""
            pts = getattr(p, "points", None)
            if pts is None:
                pts = getattr(p, "total_points", None)
            try:
                ptsf = float(pts) if pts is not None else float("-inf")
            except Exception:
                ptsf = float("-inf")
            if best is None or ptsf > best[1]:
                best = (str(name) if name else "—", ptsf)
    except Exception:
        return None
    return best


def _box_scores(lg: "League", week: int):
    """
    Prefer box_scores (richer); fall back to scoreboard if needed.
    """
    try:
        return lg.box_scores(week=week)
    except Exception:
        return getattr(lg, "scoreboard", lambda week=None: [])(week=week)


def fetch_week_from_espn(
    league_id: int,
    year: int,
    espn_s2: str = "",
    swid: str = "",
    week: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Return list of dicts for the requested (or last completed) week:
    Each game dict includes:
        home, away, hs, as, home_score, away_score
        top_home, top_away, bust, keyplay, def  (optional strings)
    """
    lg = connect_league(league_id, year, espn_s2, swid)
    if week is None:
        week = _latest_completed_week(lg)

    games: List[Dict[str, Any]] = []
    for bs in _box_scores(lg, week=week) or []:
        # Try to read via attributes; fall back to dict access if necessary
        home_team = getattr(bs, "home_team", None) or (bs.get("home_team") if isinstance(bs, dict) else None)
        away_team = getattr(bs, "away_team", None) or (bs.get("away_team") if isinstance(bs, dict) else None)

        home_name = _name_of(home_team)
        away_name = _name_of(away_team)

        hs = getattr(bs, "home_score", None)
        if hs is None and isinstance(bs, dict):
            hs = bs.get("home_score")
        as_ = getattr(bs, "away_score", None)
        if as_ is None and isinstance(bs, dict):
            as_ = bs.get("away_score")

        # Lineups for top scorers
        home_line = getattr(bs, "home_lineup", None) or (bs.get("home_lineup") if isinstance(bs, dict) else None)
        away_line = getattr(bs, "away_lineup", None) or (bs.get("away_lineup") if isinstance(bs, dict) else None)

        th = _max_player(home_line)
        ta = _max_player(away_line)

        top_home = f"{th[0]} ({th[1]:.1f})" if th else ""
        top_away = f"{ta[0]} ({ta[1]:.1f})" if ta else ""

        g: Dict[str, Any] = {
            "home": home_name,
            "away": away_name,
            "hs": hs,
            "as": as_,                   # keep legacy key for existing templates
            "home_score": hs,            # friendlier synonyms
            "away_score": as_,
            "top_home": top_home,
            "top_away": top_away,
            "bust": "",                  # optional; fill elsewhere if you compute it
            "keyplay": "",
            "def": "",
        }
        games.append(g)

    return games


# ---------------- Context builder ----------------

def _compute_awards(games: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Simple awards block: top score, low score, and largest gap.
    """
    top_team = {"team": "", "points": 0.0}
    low_team = {"team": "", "points": 0.0}
    largest_gap = {"desc": "", "gap": 0.0}

    have_low = False

    for g in games:
        try:
            hs = float(g.get("hs") if g.get("hs") is not None else "nan")
            as_ = float(g.get("as") if g.get("as") is not None else "nan")
        except Exception:
            continue

        # Track top/low teams among participants
        pairs = [(g.get("home", ""), hs), (g.get("away", ""), as_)]
        for team, pts in pairs:
            if pts != pts:  # NaN check
                continue
            if pts > top_team["points"]:
                top_team = {"team": team, "points": pts}
            if not have_low or pts < low_team["points"]:
                low_team = {"team": team, "points": pts}
                have_low = True

        # Largest margin
        if hs == hs and as_ == as_:
            gap = abs(hs - as_)
            desc = f"{g.get('home','')} vs {g.get('away','')}"
            if gap > largest_gap["gap"]:
                largest_gap = {"desc": desc, "gap": gap}

    return {
        "top_score": top_team,
        "low_score": low_team,
        "largest_gap": largest_gap,
    }


def build_context(cfg: Dict[str, Any], games: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Normalize a league+week dataset into the context the renderer expects.
    Required keys used by the runner/template:
      - name, week_num (int), week (label), date (optional)
      - games: list of dicts with keys from fetch_week_from_espn()
      - awards: {top_score, low_score, largest_gap}
      - (optional) intro text
    """
    league_name = cfg.get("name") or f"league_{cfg.get('league_id','')}"
    week_num = cfg.get("week_num") or cfg.get("week") or cfg.get("completed_week")  # flexible
    try:
        week_num = int(week_num) if week_num is not None else None
    except Exception:
        week_num = None

    # If no explicit label, synthesize something simple. Runner can override via CLI.
    week_label = cfg.get("week_label") or (f"{week_num}" if week_num is not None else "")

    # Optional ESPN cookies retained in context (runner doesn’t need them, but harmless)
    espn_s2 = cfg.get("espn_s2", "")
    swid = cfg.get("swid", "")

    # Optionally enrich games with mascot blurbs (short, neutral)
    enriched_games: List[Dict[str, Any]] = []
    for g in games:
        g2 = dict(g)  # shallow copy
        if not g2.get("blurb"):
            h_desc = _mascot_for(g2.get("home", "")) or ""
            a_desc = _mascot_for(g2.get("away", "")) or ""
            if h_desc or a_desc:
                g2["blurb"] = f"{g2.get('home','')} ({h_desc}) vs {g2.get('away','')} ({a_desc})."
            else:
                g2["blurb"] = ""
        # Provide both names for scores to avoid `{as}` issues in format strings
        if "away_score" not in g2:
            g2["away_score"] = g2.get("as")
        if "home_score" not in g2:
            g2["home_score"] = g2.get("hs")
        enriched_games.append(g2)

    awards = _compute_awards(enriched_games)

    ctx: Dict[str, Any] = {
        "name": league_name,
        "week_num": week_num,             # numeric week if known
        "week": week_label,               # printable label
        "date": cfg.get("date", ""),      # optional
        "intro": cfg.get("intro", ""),    # optional text (runner maps WEEKLY_INTRO)
        "games": enriched_games,
        "awards": awards,
        # carry-through (harmless)
        "espn_s2": espn_s2,
        "swid": swid,
    }

    # Legacy/title convenience
    if not ctx.get("title"):
        if week_label:
            ctx["title"] = f"{league_name} — Week {week_label}"
        elif week_num is not None:
            ctx["title"] = f"{league_name} — Week {week_num}"
        else:
            ctx["title"] = f"{league_name} — Weekly Gazette"

    return ctx
