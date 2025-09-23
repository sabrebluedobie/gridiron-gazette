#!/usr/bin/env python3
"""
weekly_recap.py — Gridiron Gazette DOCX builder aligned to multiple placeholder styles.

Fixes:
- Always populates scores + Spotlight, even if ESPN hides starters.
- Writes a wide set of alias variables so legacy/new templates both render.
- Computes weekly awards (Cupcake, Kitty, Top Score) from available scores.

Inputs honored: TEAM_LOGOS_FILE / team_logos.json, logos in ./logos/team_logos/*
Output: OUTDOCX may be a directory OR a filename with tokens {week},{week02},{year},{league}.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

import gazette_data
import logo_resolver
import storymaker


def _safe(s): return "" if s is None else str(s)
def _inline(doc, path: Optional[str], w_mm: float) -> Optional[InlineImage]:
    return InlineImage(doc, str(Path(path)), width=Mm(w_mm)) if path and Path(path).exists() else None

# ---------------- Logos ----------------

def _attach_team_logos(doc, games: List[Dict[str, Any]]) -> None:
    for g in games:
        home = g.get("HOME_TEAM_NAME", "")
        away = g.get("AWAY_TEAM_NAME", "")
        g["HOME_LOGO"] = _inline(doc, logo_resolver.team_logo(home), 22.0)
        g["AWAY_LOGO"] = _inline(doc, logo_resolver.team_logo(away), 22.0)

def _attach_special_logos(doc, ctx: Dict[str, Any]) -> None:
    league_name = ctx.get("LEAGUE_NAME") or ctx.get("LEAGUE_LOGO_NAME") or "Gridiron Gazette"
    ctx["LEAGUE_LOGO"]  = _inline(doc, logo_resolver.league_logo(league_name), 28.0)
    ctx["SPONSOR_LOGO"] = _inline(doc, logo_resolver.sponsor_logo("Gridiron Gazette"), 26.0)
    ctx.setdefault("SPONSOR_LINE", "")

# ---------------- Spotlight helpers ----------------

def _compute_top_bust_from_board(league: Any, week: int) -> List[Dict[str, str]]:
    """Optional: compute TOP/BUST when ESPN exposes starters; otherwise empty list."""
    out: List[Dict[str, str]] = []
    try:
        board = league.scoreboard(week) if league else []
        def pts(p):  return getattr(p, "points", getattr(p, "total_points", 0)) or 0.0
        def proj(p): return getattr(p, "projected_total_points", getattr(p, "projected_points", 0)) or 0.0
        for m in board:
            entry = {"TOP_HOME":"", "TOP_AWAY":"", "BUST":""}
            for side in ("home_team","away_team"):
                t = getattr(m, side, None)
                starters = getattr(t, "starters", []) or []
                if starters:
                    top = max(starters, key=pts)
                    bust = min(starters, key=lambda p: pts(p)-proj(p))
                    def fmt(p):
                        P = pts(p); R = proj(p)
                        return f"{getattr(p,'name','?')} ({P:.1f}" + (f" vs {R:.1f} proj)" if R else " pts)")
                    if side=="home_team": entry["TOP_HOME"]=fmt(top)
                    else: entry["TOP_AWAY"]=fmt(top)
                    if not entry["BUST"]: entry["BUST"]=fmt(bust)
            out.append(entry)
    except Exception:
        pass
    return out

def _fill_spotlight_fallbacks(games: List[Dict[str, Any]]) -> None:
    """Guarantee Spotlight fields exist by using team scores/names if player data is missing."""
    for g in games:
        home = g.get("HOME_TEAM_NAME") or "Home"
        away = g.get("AWAY_TEAM_NAME") or "Away"
        hs   = _safe(g.get("HOME_SCORE") or "0")
        as_  = _safe(g.get("AWAY_SCORE") or "0")

        g.setdefault("TOP_HOME",  f"{home}: {hs} pts (team)")
        g.setdefault("TOP_AWAY",  f"{away}: {as_} pts (team)")

        if not g.get("BUST"):
            try:
                hsf = float(hs); asf = float(as_)
                loser_name, loser_pts = (home, hsf) if hsf <= asf else (away, asf)
                g["BUST"] = f"{loser_name}: {loser_pts:.1f} pts (team)"
            except Exception:
                g["BUST"] = f"{home if str(hs) <= str(as_) else away}: {min(hs, as_)} pts (team)"

        if not g.get("KEYPLAY") and not g.get("KEY_PLAY"):
            recap = (g.get("RECAP") or g.get("BLURB") or "").strip()
            g["KEYPLAY"] = (recap.split(".")[0] + ".") if recap else "Turning point: late momentum swing decided it."

        if not g.get("DEF") and not g.get("DEF_NOTE"):
            try:
                hsf = float(hs); asf = float(as_)
                winner, loser, lpts = (home, away, asf) if hsf >= asf else (away, home, hsf)
                g["DEF"] = f"{winner} defense forced key stops, holding {loser} to {lpts:.1f}."
            except Exception:
                g["DEF"] = "Defense held firm in the clutch."

# ---------------- Template mapping + aliases ----------------

def _float_or_none(x) -> Optional[float]:
    try:
        return float(x)
    except Exception:
        return None

def _make_aliases(ctx: Dict[str, Any]) -> None:
    """
    Writes MANY alias variable names so different docx templates all fill.
    For each matchup i=1..10 we set:
      MATCHUP{i}_{HOME,AWAY,HS,AS,HOME_LOGO,AWAY_LOGO,BLURB,TOP_HOME,TOP_AWAY,BUST,KEYPLAY,DEF}
      plus aliases:
      HOME{i}, AWAY{i}, HOME_SCORE{i}, AWAY_SCORE{i},
      TEAM{i}_HOME, TEAM{i}_AWAY, SCORE{i}_HOME, SCORE{i}_AWAY,
      TOP_{i}_HOME, TOP_{i}_AWAY, BUST_{i}, KEYPLAY_{i}, DEF_{i}
    Also computes Cupcake/Kitty/Top Score awards.
    """
    games: List[Dict[str, Any]] = ctx.get("GAMES", [])
    # Per-matchup aliases
    for i in range(10):
        g = games[i] if i < len(games) else {}
        n = i + 1

        home = _safe(g.get("HOME_TEAM_NAME"))
        away = _safe(g.get("AWAY_TEAM_NAME"))
        hs   = _safe(g.get("HOME_SCORE"))
        as_  = _safe(g.get("AWAY_SCORE"))
        blb  = _safe(g.get("RECAP") or g.get("BLURB"))
        th   = _safe(g.get("TOP_HOME"))
        ta   = _safe(g.get("TOP_AWAY"))
        bust = _safe(g.get("BUST"))
        key  = _safe(g.get("KEYPLAY") or g.get("KEY_PLAY"))
        dfn  = _safe(g.get("DEF") or g.get("DEF_NOTE"))

        # Canonical names (your newer template)
        ctx[f"MATCHUP{n}_HOME"] = home
        ctx[f"MATCHUP{n}_AWAY"] = away
        ctx[f"MATCHUP{n}_HS"]   = hs
        ctx[f"MATCHUP{n}_AS"]   = as_
        ctx[f"MATCHUP{n}_HOME_LOGO"] = g.get("HOME_LOGO")
        ctx[f"MATCHUP{n}_AWAY_LOGO"] = g.get("AWAY_LOGO")
        ctx[f"MATCHUP{n}_BLURB"]     = blb
        ctx[f"MATCHUP{n}_TOP_HOME"]  = th
        ctx[f"MATCHUP{n}_TOP_AWAY"]  = ta
        ctx[f"MATCHUP{n}_BUST"]      = bust
        ctx[f"MATCHUP{n}_KEYPLAY"]   = key
        ctx[f"MATCHUP{n}_DEF"]       = dfn

        # Older/alternate names (aliases)
        ctx[f"HOME{n}"] = home
        ctx[f"AWAY{n}"] = away
        ctx[f"HOME_SCORE{n}"] = hs
        ctx[f"AWAY_SCORE{n}"] = as_
        ctx[f"TEAM{n}_HOME"] = home
        ctx[f"TEAM{n}_AWAY"] = away
        ctx[f"SCORE{n}_HOME"] = hs
        ctx[f"SCORE{n}_AWAY"] = as_
        ctx[f"TOP_{n}_HOME"] = th
        ctx[f"TOP_{n}_AWAY"] = ta
        ctx[f"BUST_{n}"] = bust
        ctx[f"KEYPLAY_{n}"] = key
        ctx[f"DEF_{n}"] = dfn

    # Weekly awards from scores
    # Cupcake: lowest single-team score
    # Kitty:   largest losing margin
    # Top:     highest single-team score
    lows: List[Tuple[str, float]] = []
    highs: List[Tuple[str, float]] = []
    margins: List[Tuple[str, str, float]] = []

    for g in games:
        home = _safe(g.get("HOME_TEAM_NAME")); away = _safe(g.get("AWAY_TEAM_NAME"))
        hs = _float_or_none(g.get("HOME_SCORE")); as_ = _float_or_none(g.get("AWAY_SCORE"))
        if hs is not None: lows.append((home, hs)); highs.append((home, hs))
        if as_ is not None: lows.append((away, as_)); highs.append((away, as_))
        if hs is not None and as_ is not None:
            if hs >= as_: margins.append((away, home, hs - as_))  # away lost by (hs-as)
            else:          margins.append((home, away, as_ - hs))  # home lost by (as-hs)

    if lows:
        cupcake_team, cupcake_score = min(lows, key=lambda t: t[1])
        ctx["AWARD_CUPCAKE_TEAM"] = cupcake_team
        ctx["AWARD_CUPCAKE_SCORE"] = f"{cupcake_score:.2f}".rstrip("0").rstrip(".")
        ctx["CUPCAKE"] = f"{cupcake_team} — {ctx['AWARD_CUPCAKE_SCORE']}"
    else:
        ctx["CUPCAKE"] = "—"

    if margins:
        loser, winner, margin = max(margins, key=lambda t: t[2])
        ctx["AWARD_KITTY_LOSER_TEAM"] = loser
        ctx["AWARD_KITTY_WINNER_TEAM"] = winner
        ctx["AWARD_KITTY_MARGIN"] = f"{margin:.2f}".rstrip("0").rstrip(".")
        ctx["KITTY"] = f"{loser} to {winner} — {ctx['AWARD_KITTY_MARGIN']}"
    else:
        ctx["KITTY"] = "—"

    if highs:
        top_team, top_score = max(highs, key=lambda t: t[1])
        ctx["AWARD_TOP_TEAM"]  = top_team
        ctx["AWARD_TOP_SCORE"] = f"{top_score:.2f}".rstrip("0").rstrip(".")
        ctx["TOPSCORE"] = f"{top_team} — {ctx['AWARD_TOP_SCORE']}"
    else:
        ctx["TOPSCORE"] = "—"

# ---------------- Main ----------------

def build_weekly_recap(
    league: Any,
    league_id: int,
    year: int,
    week: int,
    template: Optional[str] = None,
    output_dir: str = "recaps",      # directory OR filename with tokens
    llm_blurbs: bool = False,
    blurb_style: str = "sabre",
    blurb_words: int = 200,
) -> str:
    doc = DocxTemplate(template or "recap_template.docx")

    # Base context: names + scores (does not depend on starters)
    ctx = gazette_data.assemble_context(str(league_id), year, week, llm_blurbs=False, blurb_style=blurb_style)
    games = ctx.get("GAMES", [])

    # Title/header fields (seen in your template)
    ctx.setdefault("WEEK_NUMBER", week)
    ctx.setdefault("title", f"Week {week} Fantasy Football Gazette — {ctx.get('LEAGUE_NAME','League')}")

    # Optional blurbs
    if llm_blurbs and games:
        try:
            blurbs = storymaker.generate_blurbs(league, year, week, style=blurb_style, max_words=blurb_words, games=games)
            for i, g in enumerate(games):
                if i < len(blurbs):
                    g["RECAP"] = blurbs[i]
        except Exception as e:
            print(f"[blurbs] fallback: {e}")

    # Optional starters-derived tidbits (OK if empty)
    try:
        derived = _compute_top_bust_from_board(league, week)
        for i, g in enumerate(games):
            if i < len(derived):
                g.setdefault("TOP_HOME", derived[i].get("TOP_HOME",""))
                g.setdefault("TOP_AWAY", derived[i].get("TOP_AWAY",""))
                g.setdefault("BUST",     derived[i].get("BUST",""))
    except Exception:
        pass

    # Logos & Spotlight fallbacks
    _attach_team_logos(doc, games)
    ctx["GAMES"] = games
    _fill_spotlight_fallbacks(games)

    # Sponsor/league logos
    _attach_special_logos(doc, ctx)

    # Map MANY aliases so whatever your DOCX expects will be filled
    _make_aliases(ctx)

    # Output naming with tokens
    league_name = (ctx.get("LEAGUE_NAME") or ctx.get("LEAGUE_LOGO_NAME") or "League").strip()
    tokens = {"week": str(week), "week02": f"{week:02d}", "year": str(year), "league": league_name}
    def fill_tokens(s: str) -> str:
        for k, v in tokens.items():
            s = s.replace("{"+k+"}", v)
        return s

    out_hint = Path(output_dir)
    if out_hint.suffix.lower() == ".docx":
        out_path = Path(fill_tokens(str(out_hint)))
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        d = out_hint
        d.mkdir(parents=True, exist_ok=True)
        out_path = d / f"gazette_week_{week}.docx"

    doc.render(ctx)
    doc.save(out_path)
    return str(out_path)
