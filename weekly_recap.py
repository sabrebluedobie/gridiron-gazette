#!/usr/bin/env python3
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
    p = Path(path) if path else None
    return InlineImage(doc, str(p), width=Mm(w_mm)) if (p and p.exists()) else None

def _attach_team_logos(doc, games: List[Dict[str, Any]]) -> None:
    for g in games:
        g["HOME_LOGO"] = _inline(doc, logo_resolver.team_logo(g.get("HOME_TEAM_NAME","")), 22.0)
        g["AWAY_LOGO"] = _inline(doc, logo_resolver.team_logo(g.get("AWAY_TEAM_NAME","")), 22.0)

def _attach_special_logos(doc, ctx: Dict[str, Any]) -> None:
    import json
    m = {}
    tl = Path("team_logos.json")
    if tl.exists():
        try: m = json.loads(tl.read_text(encoding="utf-8"))
        except Exception: m = {}
    league_name = ctx.get("LEAGUE_NAME") or ctx.get("LEAGUE_LOGO_NAME") or "Gridiron Gazette"
    ctx["LEAGUE_LOGO"]  = _inline(doc, m.get("LEAGUE_LOGO")  or logo_resolver.league_logo(league_name), 28.0)
    ctx["SPONSOR_LOGO"] = _inline(doc, m.get("SPONSOR_LOGO") or logo_resolver.sponsor_logo("Gridiron Gazette"), 26.0)

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
    out: List[Dict[str, str]] = []
    try:
        if not league: return out
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
                    def fmt(p): return f"{getattr(p,'name','?')} ({pts(p):.1f} vs {proj(p):.1f} proj)" if proj(p) else f"{getattr(p,'name','?')} ({pts(p):.1f} pts)"
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
    output_dir: str = "recaps",   # may be a directory OR a filename with {tokens}
    llm_blurbs: bool = False,
    blurb_style: str = "sabre",
    blurb_words: int = 200,
) -> str:
    template_path = template or "recap_template.docx"
    doc = DocxTemplate(template_path)

    ctx = gazette_data.assemble_context(str(league_id), year, week, llm_blurbs=False, blurb_style=blurb_style)
    games = ctx.get("GAMES", [])

    if llm_blurbs and games:
        try:
            blurbs = storymaker.generate_blurbs(league, year, week, style=blurb_style, max_words=blurb_words, games=games)
            for i, g in enumerate(games):
                if i < len(blurbs):
                    g["RECAP"] = blurbs[i]
        except Exception as e:
            print(f"[blurbs] fallback to basic recaps: {e}")

    derived = _compute_top_bust_from_board(league, week)
    for i, g in enumerate(games):
        if i < len(derived):
            g.setdefault("TOP_HOME", derived[i].get("TOP_HOME",""))
            g.setdefault("TOP_AWAY", derived[i].get("TOP_AWAY",""))
            g.setdefault("BUST",     derived[i].get("BUST",""))

    _attach_team_logos(doc, games)
    ctx["GAMES"] = games
    ctx.setdefault("LEAGUE_LOGO_NAME", ctx.get("LEAGUE_NAME", "Gridiron Gazette"))
    _attach_special_logos(doc, ctx)
    _map_front_page_slots(ctx)

    # --------- filename logic (supports tokens) ----------
    from pathlib import Path
    out_hint = Path(output_dir)
    league_name = (ctx.get("LEAGUE_NAME") or ctx.get("LEAGUE_LOGO_NAME") or "League").strip()

    # Build token map (simple + padded week)
    tokens = {
        "week": str(week),
        "week02": f"{week:02d}",
        "year": str(year),
        "league": league_name,
    }

    def fill_tokens(s: str) -> str:
        # minimal safe formatter for {week}, {week02}, {year}, {league}
        for k, v in tokens.items():
            s = s.replace("{"+k+"}", v)
        return s

    if out_hint.suffix.lower() == ".docx":
        # Treat OUTDOCX as a FILENAME template (apply tokens)
        out_path = Path(fill_tokens(str(out_hint)))
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        # Treat OUTDOCX as a DIRECTORY
        d = out_hint
        d.mkdir(parents=True, exist_ok=True)
        out_path = d / f"gazette_week_{week}.docx"
    # -----------------------------------------------------

    doc.render(ctx)
    doc.save(out_path)
    return str(out_path)


    ctx = gazette_data.assemble_context(str(league_id), year, week, llm_blurbs=False, blurb_style=blurb_style)
    games = ctx.get("GAMES", [])

    # Prefer LLM blurbs; fall back gracefully if League (or players) isn’t available
    if llm_blurbs and games:
        try:
            blurbs = storymaker.generate_blurbs(league, year, week, style=blurb_style, max_words=blurb_words, games=games)
            for i, g in enumerate(games):
                if i < len(blurbs):
                    g["RECAP"] = blurbs[i]
        except Exception as e:
            print(f"[blurbs] fallback to basic recaps: {e}")

    # Compute top/bust only if we can see starters
    derived = _compute_top_bust_from_board(league, week)
    for i, g in enumerate(games):
        if i < len(derived):
            g.setdefault("TOP_HOME", derived[i].get("TOP_HOME",""))
            g.setdefault("TOP_AWAY", derived[i].get("TOP_AWAY",""))
            g.setdefault("BUST",     derived[i].get("BUST",""))

    _attach_team_logos(doc, games)
    ctx["GAMES"] = games
    ctx.setdefault("LEAGUE_LOGO_NAME", ctx.get("LEAGUE_NAME", "Gridiron Gazette"))
    _attach_special_logos(doc, ctx)
    _map_front_page_slots(ctx)

    # Save: support OUTDOCX as either folder or explicit filename
    out_hint = Path(output_dir)
    if out_hint.suffix.lower() == ".docx":
        out_path = out_hint
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        d = out_hint
        d.mkdir(parents=True, exist_ok=True)
        out_path = d / f"gazette_week_{week}.docx"

    doc.render(ctx)
    doc.save(out_path)
    return str(out_path)
