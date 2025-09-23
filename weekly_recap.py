from __future__ import annotations
from pathlib import Path
from typing import Any, Dict

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

from gazette_data import build_context
import logo_resolver as logos


def _make_aliases(ctx: Dict[str, Any]) -> None:
    week = ctx.get("WEEK_NUMBER")
    league = ctx.get("LEAGUE_NAME") or "League"
    ctx.setdefault("TITLE", f"Week {week} Fantasy Football Gazette — {league}")
    ctx.setdefault("SUBTITLE", "For those times when everyone wants to know your score.")
    for i in range(1, 8):
        for a, b in (
            (f"HOME{i}",        f"MATCHUP{i}_HOME"),
            (f"AWAY{i}",        f"MATCHUP{i}_AWAY"),
            (f"HNAME{i}",       f"MATCHUP{i}_HOME"),
            (f"ANAME{i}",       f"MATCHUP{i}_AWAY"),
        ):
            if b in ctx and a not in ctx:
                ctx[a] = ctx[b]
        for a, b in (
            (f"HS{i}",          f"MATCHUP{i}_HS"),
            (f"AS{i}",          f"MATCHUP{i}_AS"),
            (f"HOME{i}_SCORE",  f"MATCHUP{i}_HS"),
            (f"AWAY{i}_SCORE",  f"MATCHUP{i}_AS"),
        ):
            if b in ctx and a not in ctx:
                ctx[a] = ctx[b]
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
    awards = {
        "CUPCAKE":         ctx.get("CUPCAKE_LINE", "—"),
        "KITTY":           ctx.get("KITTY_LINE", "—"),
        "TOPSCORE":        ctx.get("TOPSCORE_LINE", "—"),
        "AWARD_CUPCAKE":   ctx.get("CUPCAKE_LINE", "—"),
        "AWARD_KITTY":     ctx.get("KITTY_LINE", "—"),
        "AWARD_TOPSCORE":  ctx.get("TOPSCORE_LINE", "—"),
        "CUPCAKE_TEAM":    ctx.get("AWARD_CUPCAKE_TEAM", ""),
        "CUPCAKE_SCORE":   ctx.get("AWARD_CUPCAKE_SCORE", ""),
        "KITTY_LOSER":     ctx.get("AWARD_KITTY_LOSER", ""),
        "KITTY_WINNER":    ctx.get("AWARD_KITTY_WINNER", ""),
        "KITTY_GAP":       ctx.get("AWARD_KITTY_GAP", ""),
        "TOPSCORE_TEAM":   ctx.get("AWARD_TOPSCORE_TEAM", ""),
        "TOPSCORE_POINTS": ctx.get("AWARD_TOPSCORE_POINTS", ""),
    }
    for k, v in awards.items():
        ctx.setdefault(k, v)


def _attach_images(ctx: Dict[str, Any], doc: DocxTemplate) -> None:
    # League & sponsor
    league_name = str(ctx.get("LEAGUE_NAME") or "")
    sponsor_name = str(ctx.get("SPONSOR_NAME") or "Gridiron Gazette")

    lg = logos.league_logo(league_name)
    if lg and Path(lg).exists():
        ctx["LEAGUE_LOGO"] = InlineImage(doc, lg, width=Mm(25))

    sp = logos.sponsor_logo(sponsor_name)
    if sp and Path(sp).exists():
        ctx["SPONSOR_LOGO"] = InlineImage(doc, sp, width=Mm(25))

    # Team logos per matchup
    for i in range(1, 8):
        hkey, akey = f"MATCHUP{i}_HOME", f"MATCHUP{i}_AWAY"
        if hkey in ctx and ctx[hkey]:
            hp = logos.team_logo(str(ctx[hkey]))
            if hp and Path(hp).exists():
                ctx[f"MATCHUP{i}_HOME_LOGO"] = InlineImage(doc, hp, width=Mm(22))
        if akey in ctx and ctx[akey]:
            ap = logos.team_logo(str(ctx[akey]))
            if ap and Path(ap).exists():
                ctx[f"MATCHUP{i}_AWAY_LOGO"] = InlineImage(doc, ap, width=Mm(22))


def render_docx(template_path: str, outdocx: str, context: Dict[str, Any]) -> str:
    # Create ONE DocxTemplate instance and reuse for images + render
    doc = DocxTemplate(template_path)
    _make_aliases(context)
    _attach_images(context, doc)
    Path(outdocx).parent.mkdir(parents=True, exist_ok=True)
    doc.render(context)
    doc.save(outdocx)
    return outdocx


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
    ctx = build_context(league_id=league_id, year=year, week=week)
    ctx.setdefault("BLURB_STYLE", blurb_style)
    ctx.setdefault("BLURB_WORDS", blurb_words)

    week_num = int(ctx.get("WEEK_NUMBER", week or 0) or 0)
    league_name = ctx.get("LEAGUE_NAME", "League")
    out_token = output_dir
    out_token = out_token.replace("{year}", str(ctx.get("YEAR", year)))
    out_token = out_token.replace("{league}", str(league_name))
    out_token = out_token.replace("{week}", str(week_num))
    out_token = out_token.replace("{week02}", f"{week_num:02d}")
    out_path = (
        out_token
        if out_token.lower().endswith(".docx")
        else str(Path(out_token) / f"gazette_week_{week_num}.docx")
    )

    return render_docx(template, out_path, ctx)
