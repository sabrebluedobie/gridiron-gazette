# weekly_recap.py
from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict

from docxtpl import DocxTemplate

from gazette_data import build_context

# --------------------------------
# Alias layer (template resiliency)
# --------------------------------
def _make_aliases(ctx: Dict[str, Any]) -> None:
    """
    Populate extra keys so older/newer DOCX templates with different
    placeholder names still get values. Non-destructive.
    """
    week = ctx.get("WEEK_NUMBER")
    league = ctx.get("LEAGUE_NAME") or "League"

    # Title/subtitle fallbacks
    ctx.setdefault("TITLE", f"Week {week} Fantasy Football Gazette — {league}")
    ctx.setdefault("SUBTITLE", "For those times when everyone wants to know your score.")

    # Per-matchup flexible keys (cover 1..7)
    for i in range(1, 8):
        # Names
        for a, b in (
            (f"HOME{i}",        f"MATCHUP{i}_HOME"),
            (f"AWAY{i}",        f"MATCHUP{i}_AWAY"),
            (f"HNAME{i}",       f"MATCHUP{i}_HOME"),
            (f"ANAME{i}",       f"MATCHUP{i}_AWAY"),
        ):
            if b in ctx and a not in ctx:
                ctx[a] = ctx[b]

        # Scores
        for a, b in (
            (f"HS{i}",          f"MATCHUP{i}_HS"),
            (f"AS{i}",          f"MATCHUP{i}_AS"),
            (f"HOME{i}_SCORE",  f"MATCHUP{i}_HS"),
            (f"AWAY{i}_SCORE",  f"MATCHUP{i}_AS"),
        ):
            if b in ctx and a not in ctx:
                ctx[a] = ctx[b]

        # Top scorers (multiple variants)
        alias_pairs = [
            (f"MATCHUP{i}_TOP_SCORER_HOME", f"MATCHUP{i}_HOME_TOP_SCORER"),
            (f"MATCHUP{i}_TOP_SCORER_AWAY", f"MATCHUP{i}_AWAY_TOP_SCORER"),
            (f"MATCHUP{i}_TOP_POINTS_HOME", f"MATCHUP{i}_HOME_TOP_POINTS"),
            (f"MATCHUP{i}_TOP_POINTS_AWAY", f"MATCHUP{i}_AWAY_TOP_POINTS"),
            (f"TOP_SCORER_HOME_{i}",        f"MATCHUP{i}_HOME_TOP_SCORER"),
            (f"TOP_SCORER_AWAY_{i}",        f"MATCHUP{i}_AWAY_TOP_SCORER"),
            (f"TOP_POINTS_HOME_{i}",        f"MATCHUP{i}_HOME_TOP_POINTS"),
            (f"TOP_POINTS_AWAY_{i}",        f"MATCHUP{i}_AWAY_TOP_POINTS"),
        ]
        for a, b in alias_pairs:
            if b in ctx and a not in ctx:
                ctx[a] = ctx[b]

    # Awards: provide multiple popular keys
    awards = {
        "CUPCAKE":       ctx.get("CUPCAKE_LINE", "—"),
        "KITTY":         ctx.get("KITTY_LINE", "—"),
        "TOPSCORE":      ctx.get("TOPSCORE_LINE", "—"),
        "AWARD_CUPCAKE": ctx.get("CUPCAKE_LINE", "—"),
        "AWARD_KITTY":   ctx.get("KITTY_LINE", "—"),
        "AWARD_TOPSCORE":ctx.get("TOPSCORE_LINE", "—"),
        "CUPCAKE_TEAM":  ctx.get("AWARD_CUPCAKE_TEAM", ""),
        "CUPCAKE_SCORE": ctx.get("AWARD_CUPCAKE_SCORE", ""),
        "KITTY_LOSER":   ctx.get("AWARD_KITTY_LOSER", ""),
        "KITTY_WINNER":  ctx.get("AWARD_KITTY_WINNER", ""),
        "KITTY_GAP":     ctx.get("AWARD_KITTY_GAP", ""),
        "TOPSCORE_TEAM": ctx.get("AWARD_TOPSCORE_TEAM", ""),
        "TOPSCORE_POINTS": ctx.get("AWARD_TOPSCORE_POINTS", ""),
    }
    for k, v in awards.items():
        ctx.setdefault(k, v)

def render_docx(template_path: str, outdocx: str, context: Dict[str, Any]) -> str:
    doc = DocxTemplate(template_path)
    _make_aliases(context)
    Path(outdocx).parent.mkdir(parents=True, exist_ok=True)
    doc.render(context)
    doc.save(outdocx)
    return outdocx

# --------------------------------
# Public entry point
# --------------------------------

def build_weekly_recap(
    league: Any,
    league_id: int,
    year: int,
    week: int,
    template: str,
    output_dir: str,
    llm_blurbs: bool = True,
    blurb_style: str = "sabre",
    blurb_words: int = 200,
) -> str:
    """
    Assemble context and render the weekly recap into DOCX.
    Note: Sabre blurbs are handled elsewhere; this focuses on ESPN data + awards.
    """
    ctx = build_context(league_id=league_id, year=year, week=week)

    # Basic title and footer adornments (non-intrusive)
    ctx.setdefault("BLURB_STYLE", blurb_style)
    ctx.setdefault("BLURB_WORDS", blurb_words)

    # Support tokens in output (Week{week}, {week02}, {year}, {league})
    week_num = int(ctx.get("WEEK_NUMBER", week or 0) or 0)
    league_name = ctx.get("LEAGUE_NAME", "League")
    out_token = output_dir
    out_token = out_token.replace("{year}", str(ctx.get("YEAR", year)))
    out_token = out_token.replace("{league}", str(league_name))
    out_token = out_token.replace("{week}", str(week_num))
    out_token = out_token.replace("{week02}", f"{week_num:02d}")
    out_path = out_token if out_token.lower().endswith(".docx") else str(Path(out_token) / f"gazette_week_{week_num}.docx")

    return render_docx(template, out_path, ctx)
