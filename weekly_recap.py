#!/usr/bin/env python3
"""
weekly_recap.py — renders the Gazette DOCX (logos + blurbs + stats wired to template)

- Pulls game data via gazette_data (resilient ESPN access & sample fallback).
- Optionally generates Sabre blurbs via storymaker (from the actual League object).
- Resolves logos (league, sponsor, team) and inserts InlineImages.
- Maps per-game fields into the template's front-page MATCHUPn_* placeholders.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from docxtpl import DocxTemplate, InlineImage  # pip install docxtpl
from docx.shared import Mm

import gazette_data
import logo_resolver
import storymaker


# ---------- helpers ----------

def _safe(val: Optional[str]) -> str:
    return val or ""


def _compute_top_bust_from_board(league: Any, week: int) -> List[Dict[str, str]]:
    """
    Returns a list of dicts (one per matchup in scoreboard order)
    with TOP_HOME, TOP_AWAY, BUST fields derived from starters.
    """
    board = league.scoreboard(week)
    out: List[Dict[str, str]] = []

    def pts(p): return getattr(p, "points", getattr(p, "total_points", 0)) or 0.0
    def proj(p): return getattr(p, "projected_total_points", getattr(p, "projected_points", 0)) or 0.0

    for m in board:
        entry = {"TOP_HOME": "", "TOP_AWAY": "", "BUST": ""}
        home, away = getattr(m, "home_team", None), getattr(m, "away_team", None)

        def top_and_bust(team):
            starters = getattr(team, "starters", []) or []
            if not starters:
                return None, None
            top = max(starters, key=pts)
            bust = min(starters, key=lambda p: pts(p) - proj(p))
            def fmt(p): return f"{getattr(p,'name','?')} ({pts(p):.1f} vs {proj(p):.1f} proj)"
            return fmt(top), fmt(bust)

        if home:
            th, bh = top_and_bust(home)
            if th: entry["TOP_HOME"] = th
            if bh: entry["BUST"] = bh  # prefer home bust; away may overwrite if home empty

        if away:
            ta, ba = top_and_bust(away)
            if ta: entry["TOP_AWAY"] = ta
            if ba and not entry["BUST"]: entry["BUST"] = ba

        out.append(entry)

    return out


def _inline(doc: DocxTemplate, path: Optional[str], width_mm: float = 22.0) -> Optional[InlineImage]:
    if not path or not Path(path).exists():
        return None
    return InlineImage(doc, path, width=Mm(width_mm))


def _attach_team_logos(doc: DocxTemplate, games: List[Dict[str, Any]]) -> None:
    for g in games:
        home = g.get("HOME_TEAM_NAME", "")
        away = g.get("AWAY_TEAM_NAME", "")
        g["HOME_LOGO"] = _inline(doc, logo_resolver.team_logo(home), 22.0)
        g["AWAY_LOGO"] = _inline(doc, logo_resolver.team_logo(away), 22.0)


def _attach_special_logos(doc: DocxTemplate, ctx: Dict[str, Any]) -> None:
    """
    Prefer explicit mappings in team_logos.json for LEAGUE_LOGO / SPONSOR_LOGO;
    otherwise fall back to resolver using the league name.
    """
    # load the mapping file if present
    special_map = {}
    tl = Path("team_logos.json")
    if tl.exists():
        try:
            import json
            special_map = json.loads(tl.read_text(encoding="utf-8"))
        except Exception:
            special_map = {}

    league_name = ctx.get("LEAGUE_NAME") or ctx.get("LEAGUE_LOGO_NAME") or "Gridiron Gazette"
    league_logo_path = special_map.get("LEAGUE_LOGO") or logo_resolver.league_logo(league_name)
    sponsor_logo_path = special_map.get("SPONSOR_LOGO") or logo_resolver.sponsor_logo("Gridiron Gazette")

    ctx["LEAGUE_LOGO"] = _inline(doc, league_logo_path, 28.0)
    ctx["SPONSOR_LOGO"] = _inline(doc, sponsor_logo_path, 26.0)


def _map_front_page_slots(ctx: Dict[str, Any]) -> None:
    """Copy per-game fields into MATCHUPn_* placeholders used by the template."""
    games = ctx.get("GAMES", [])
    for i in range(10):  # template supports up to 10 slots safely
        g = games[i] if i < len(games) else {}
        n = i + 1
        ctx[f"MATCHUP{n}_HOME"] = _safe(g.get("HOME_TEAM_NAME"))
        ctx[f"MATCHUP{n}_AWAY"] = _safe(g.get("AWAY_TEAM_NAME"))
        ctx[f"MATCHUP{n}_HS"]   = _safe(g.get("HOME_SCORE"))
        ctx[f"MATCHUP{n}_AS"]   = _safe(g.get("AWAY_SCORE"))

        # Logos (InlineImage or None)
        ctx[f"MATCHUP{n}_HOME_LOGO"] = g.get("HOME_LOGO")
        ctx[f"MATCHUP{n}_AWAY_LOGO"] = g.get("AWAY_LOGO")

        # Blurbs (LLM or basic)
        ctx[f"MATCHUP{n}_BLURB"] = _safe(g.get("RECAP") or g.get("BLURB"))

        # Player call-outs (derive if missing)
        ctx[f"MATCHUP{n}_TOP_HOME"] = _safe(g.get("TOP_HOME"))
        ctx[f"MATCHUP{n}_TOP_AWAY"] = _safe(g.get("TOP_AWAY"))
        ctx[f"MATCHUP{n}_BUST"]     = _safe(g.get("BUST"))
        ctx[f"MATCHUP{n}_KEYPLAY"]  = _safe(g.get("KEYPLAY") or g.get("KEY_PLAY"))
        ctx[f"MATCHUP{n}_DEF"]      = _safe(g.get("DEF") or g.get("DEF_NOTE"))


# ---------- main entry ----------

def build_weekly_recap(
    league: Any,
    league_id: int,
    year: int,
    week: int,
    template: Optional[str] = None,
    output_dir: str = "recaps",
    llm_blurbs: bool = False,
    blurb_style: str = "sabre",
    blurb_words: int = 200,
) -> str:
    """
    Produces the final DOCX and returns its path.
    """
    template_path = template or "recap_template.docx"
    if not Path(template_path).exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    # 1) Fetch data (resilient ESPN access + sample fallback)
    ctx = gazette_data.assemble_context(str(league_id), year, week, llm_blurbs=False, blurb_style=blurb_style)
    games = ctx.get("GAMES", [])  # a list of dicts with HOME/ AWAY / SCORES / RECAP (basic)

    # 2) Optionally replace basic RECAPs with Sabre LLM blurbs derived from the real League object
    if llm_blurbs and games:
        try:
            blurbs = storymaker.generate_blurbs(league, year, week, style=blurb_style, max_words=blurb_words)
            for i, g in enumerate(games):
                if i < len(blurbs):
                    g["RECAP"] = blurbs[i]
        except Exception as e:
            print(f"[blurbs] Falling back to basic recaps: {e}")

    # 3) Derive per-matchup player call-outs from the League starters if missing
    try:
        derived = _compute_top_bust_from_board(league, week)
        for i, g in enumerate(games):
            if i < len(derived):
                g.setdefault("TOP_HOME", derived[i].get("TOP_HOME", ""))
                g.setdefault("TOP_AWAY", derived[i].get("TOP_AWAY", ""))
                g.setdefault("BUST",     derived[i].get("BUST", ""))
    except Exception as e:
        print(f"[derive] Could not compute top/bust: {e}")

    # 4) Prepare template context: images + front-page mapping + awards already in ctx
    doc = DocxTemplate(template_path)

    _attach_team_logos(doc, games)
    ctx["GAMES"] = games  # in case we mutated

    # League/sponsor logos
    ctx.setdefault("LEAGUE_LOGO_NAME", ctx.get("LEAGUE_NAME", "Gridiron Gazette"))
    _attach_special_logos(doc, ctx)

    # Map per-game fields into MATCHUPn_* expected by the template
    _map_front_page_slots(ctx)

    # 5) Render & save
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    out_path = outdir / f"gazette_week_{week}.docx"
    doc.render(ctx)
    doc.save(out_path)

    return str(out_path)
