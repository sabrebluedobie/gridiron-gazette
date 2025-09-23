#!/usr/bin/env python3
"""
updated_weekly_recap.py — Gridiron Gazette builder wired to your template

- Maps directly to placeholders used in recap_template.docx:
  title, WEEK_NUMBER, WEEKLY_INTRO,
  MATCHUP{1..10}_{HOME,AWAY,HS,AS,HOME_LOGO,AWAY_LOGO,BLURB,TOP_HOME,TOP_AWAY,BUST,KEYPLAY,DEF},
  LEAGUE_LOGO, SPONSOR_LOGO, SPONSOR_LINE

- Logos: local-first via ./logos/team_logos/ and ./logos/special/
- OUTDOCX may be a directory OR a filename with tokens:
  {week}, {week02}, {year}, {league}
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

import gazette_data
import logo_resolver
import storymaker


def _safe(s): return s or ""


def _inline(doc, path: Optional[str], w_mm: float) -> Optional[InlineImage]:
    return InlineImage(doc, str(Path(path)), width=Mm(w_mm)) if path and Path(path).exists() else None


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
    ctx.setdefault("SPONSOR_LINE", "")  # keep header tidy even if empty


def _map_front_page_slots(ctx: Dict[str, Any]) -> None:
    games = ctx.get("GAMES", [])
    for i in range(10):
        g = games[i] if i < len(games) else {}
        n = i + 1
        ctx[f"MATCHUP{n}_HOME"] = _safe(g.get("HOME_TEAM_NAME"))
        ctx[f"MATCHUP{n}_AWAY"] = _safe(g.get("AWAY_TEAM_NAME"))
        ctx[f"MATCHUP{n}_HS"]   = _safe(g.get("HOME_SCORE"))
        ctx[f"MATCHUP{n}_AS"]   = _safe(g.get("AWAY_SCORE"))
        ctx[f"MATCHUP{n}_HOME_LOGO"] = g.get("HOME_LOGO")
        ctx[f"MATCHUP{n}_AWAY_LOGO"] = g.get("AWAY_LOGO")
        ctx[f"MATCHUP{n}_BLURB"]     = _safe(g.get("RECAP") or g.get("BLURB"))
        ctx[f"MATCHUP{n}_TOP_HOME"]  = _safe(g.get("TOP_HOME"))
        ctx[f"MATCHUP{n}_TOP_AWAY"]  = _safe(g.get("TOP_AWAY"))
        ctx[f"MATCHUP{n}_BUST"]      = _safe(g.get("BUST"))
        ctx[f"MATCHUP{n}_KEYPLAY"]   = _safe(g.get("KEYPLAY") or g.get("KEY_PLAY"))
        ctx[f"MATCHUP{n}_DEF"]       = _safe(g.get("DEF") or g.get("DEF_NOTE"))


def _compute_top_bust_from_board(league: Any, week: int) -> List[Dict[str, str]]:
    """Optional: fill TOP/BUST when starters are available; otherwise silently skip."""
    out: List[Dict[str, str]] = []
    try:
        if not league:
            return out
        board = league.scoreboard(week)
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
                    def fmt(p): return f"{getattr(p,'name','?')} ({pts(p):.1f}" + (f" vs {proj(p):.1f} proj" if proj(p) else " pts") + ")"
                    if side=="home_team": entry["TOP_HOME"]=fmt(top)
                    else: entry["TOP_AWAY"]=fmt(top)
                    if not entry["BUST"]: entry["BUST"]=fmt(bust)
            out.append(entry)
    except Exception:
        pass
    return out


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
    """Main entry point called by build_gazette.py"""
    doc = DocxTemplate(template or "recap_template.docx")

    # Base context (scores + shell); doesn’t depend on starters
    ctx = gazette_data.assemble_context(str(league_id), year, week, llm_blurbs=False, blurb_style=blurb_style)
    games = ctx.get("GAMES", [])

    # Ensure header/title placeholders are provided
    ctx.setdefault("WEEK_NUMBER", week)
    ctx.setdefault("title", f"Week {week} Fantasy Football Gazette — {ctx.get('LEAGUE_NAME','League')}")

    # Blurbs: league if available; else games-only fallback inside storymaker
    if llm_blurbs and games:
        try:
            blurbs = storymaker.generate_blurbs(league, year, week, style=blurb_style, max_words=blurb_words, games=games)
            for i, g in enumerate(games):
                if i < len(blurbs):
                    g["RECAP"] = blurbs[i]
        except Exception as e:
            print(f"[blurbs] fallback: {e}")

    # Optional player-derived tidbits (if starters are visible)
    derived = _compute_top_bust_from_board(league, week)
    for i, g in enumerate(games):
        if i < len(derived):
            g.setdefault("TOP_HOME", derived[i].get("TOP_HOME",""))
            g.setdefault("TOP_AWAY", derived[i].get("TOP_AWAY",""))
            g.setdefault("BUST",     derived[i].get("BUST",""))

    # Logos (local-first), mapping to InlineImage fields
    _attach_team_logos(doc, games)
    ctx["GAMES"] = games
    _attach_special_logos(doc, ctx)
    _map_front_page_slots(ctx)

    # Output naming — supports tokens in OUTDOCX
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
