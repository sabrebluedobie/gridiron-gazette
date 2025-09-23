from __future__ import annotations
from pathlib import Path
from typing import Any, Dict

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

from gazette_data import build_context
import logo_resolver as logos

# --- Optional Sabre blurbs (storymaker) ---
try:
    from storymaker import generate_spotlights_for_week
except Exception:
    def generate_spotlights_for_week(ctx: Dict[str, Any], style: str, words: int) -> Dict[str, Dict[str, str]]:
        # Fallback: produce simple stat-based spotlights so the section is never blank
        out: Dict[str, Dict[str, str]] = {}
        for i in range(1, 8):
            h = ctx.get(f"MATCHUP{i}_HOME")
            a = ctx.get(f"MATCHUP{i}_AWAY")
            if not (h and a):
                continue
            hs = ctx.get(f"MATCHUP{i}_HS", "")
            as_ = ctx.get(f"MATCHUP{i}_AS", "")
            hts = ctx.get(f"MATCHUP{i}_HOME_TOP_SCORER", "")
            htp = ctx.get(f"MATCHUP{i}_HOME_TOP_POINTS", "")
            ats = ctx.get(f"MATCHUP{i}_AWAY_TOP_SCORER", "")
            atp = ctx.get(f"MATCHUP{i}_AWAY_TOP_POINTS", "")
            out[str(i)] = {
                "home": f"Top Scorer (Home): {hts} {f'({htp})' if htp else ''}".strip(),
                "away": f"Top Scorer (Away): {ats} {f'({atp})' if atp else ''}".strip(),
                "bust": "Biggest Bust: —",
                "key": "Key Play: —",
                "def": "Defense Note: —",
            }
        return out


def _make_aliases(ctx: Dict[str, Any]) -> None:
    week = ctx.get("WEEK_NUMBER")
    league = ctx.get("LEAGUE_NAME") or "League"
    ctx.setdefault("TITLE", f"Week {week} Fantasy Football Gazette — {league}")
    ctx.setdefault("SUBTITLE", "For those times when everyone wants to know your score.")

    # Scores & names aliases
    for i in range(1, 8):
        for a, b in (
            (f"HOME{i}",        f"MATCHUP{i}_HOME"),
            (f"AWAY{i}",        f"MATCHUP{i}_AWAY"),
            (f"HNAME{i}",       f"MATCHUP{i}_HOME"),
            (f"ANAME{i}",       f"MATCHUP{i}_AWAY"),
            (f"HS{i}",          f"MATCHUP{i}_HS"),
            (f"AS{i}",          f"MATCHUP{i}_AS"),
            (f"HOME{i}_SCORE",  f"MATCHUP{i}_HS"),
            (f"AWAY{i}_SCORE",  f"MATCHUP{i}_AS"),
        ):
            if b in ctx and a not in ctx:
                ctx[a] = ctx[b]

        # Top-scorer aliases
        for a, b in (
            (f"TOP_SCORER_HOME_{i}", f"MATCHUP{i}_HOME_TOP_SCORER"),
            (f"TOP_SCORER_AWAY_{i}", f"MATCHUP{i}_AWAY_TOP_SCORER"),
            (f"TOP_POINTS_HOME_{i}", f"MATCHUP{i}_HOME_TOP_POINTS"),
            (f"TOP_POINTS_AWAY_{i}", f"MATCHUP{i}_AWAY_TOP_POINTS"),
        ):
            if b in ctx and a not in ctx:
                ctx[a] = ctx[b]

    # Awards aliases
    awards = {
        "CUPCAKE":         ctx.get("CUPCAKE_LINE", "—"),
        "KITTY":           ctx.get("KITTY_LINE", "—"),
        "TOPSCORE":        ctx.get("TOPSCORE_LINE", "—"),
        "AWARD_CUPCAKE":   ctx.get("CUPCAKE_LINE", "—"),
        "AWARD_KITTY":     ctx.get("KITTY_LINE", "—"),
        "AWARD_TOPSCORE":  ctx.get("TOPSCORE_LINE", "—"),
    }
    for k, v in awards.items():
        ctx.setdefault(k, v)


def _attach_images(ctx: Dict[str, Any], doc: DocxTemplate) -> None:
    league_name = str(ctx.get("LEAGUE_NAME") or "")
    sponsor_name = str(ctx.get("SPONSOR_NAME") or "Gridiron Gazette")

    lg_raw = logos.league_logo(league_name)
    lg = logos.sanitize_logo_for_docx(lg_raw)
    if lg and Path(lg).exists():
        ctx["LEAGUE_LOGO"] = InlineImage(doc, lg, width=Mm(25))

    sp_raw = logos.sponsor_logo(sponsor_name)
    sp = logos.sanitize_logo_for_docx(sp_raw)
    if sp and Path(sp).exists():
        ctx["SPONSOR_LOGO"] = InlineImage(doc, sp, width=Mm(25))

    for i in range(1, 8):
        hkey, akey = f"MATCHUP{i}_HOME", f"MATCHUP{i}_AWAY"
        if hkey in ctx and ctx[hkey]:
            hp_raw = logos.team_logo(str(ctx[hkey]))
            hp = logos.sanitize_logo_for_docx(hp_raw)
            if hp and Path(hp).exists():
                ctx[f"MATCHUP{i}_HOME_LOGO"] = InlineImage(doc, hp, width=Mm(22))
        if akey in ctx and ctx[akey]:
            ap_raw = logos.team_logo(str(ctx[akey]))
            ap = logos.sanitize_logo_for_docx(ap_raw)
            if ap and Path(ap).exists():
                ctx[f"MATCHUP{i}_AWAY_LOGO"] = InlineImage(doc, ap, width=Mm(22))


def _inject_spotlights(ctx: Dict[str, Any], style: str, words: int) -> None:
    """
    Populate per-matchup spotlights. Uses LLM if available, otherwise stat fallback.
    Creates both generic keys and alias keys used by older templates.
    """
    blocks = generate_spotlights_for_week(ctx, style=style, words=words)  # { "1": {...}, ... }
    for i in range(1, 8):
        b = blocks.get(str(i), {})
        # Canonical keys expected by newer templates
        ctx.setdefault(f"SPOTLIGHT_HOME_{i}", b.get("home", ""))
        ctx.setdefault(f"SPOTLIGHT_AWAY_{i}", b.get("away", ""))
        ctx.setdefault(f"SPOTLIGHT_BUST_{i}", b.get("bust", ""))
        ctx.setdefault(f"SPOTLIGHT_KEYPLAY_{i}", b.get("key", ""))
        ctx.setdefault(f"SPOTLIGHT_DEFNOTE_{i}", b.get("def", ""))

        # Popular alias keys some docs used
        ctx.setdefault(f"MATCHUP{i}_SPOTLIGHT_HOME", ctx[f"SPOTLIGHT_HOME_{i}"])
        ctx.setdefault(f"MATCHUP{i}_SPOTLIGHT_AWAY", ctx[f"SPOTLIGHT_AWAY_{i}"])
        ctx.setdefault(f"MATCHUP{i}_SPOTLIGHT_BUST", ctx[f"SPOTLIGHT_BUST_{i}"])
        ctx.setdefault(f"MATCHUP{i}_SPOTLIGHT_KEY",  ctx[f"SPOTLIGHT_KEYPLAY_{i}"])
        ctx.setdefault(f"MATCHUP{i}_SPOTLIGHT_DEF",  ctx[f"SPOTLIGHT_DEFNOTE_{i}"])


def render_docx(template_path: str, outdocx: str, context: Dict[str, Any]) -> str:
    doc = DocxTemplate(template_path)
    _make_aliases(context)
    _inject_spotlights(context, style=context.get("BLURB_STYLE", "sabre"), words=int(context.get("BLURB_WORDS", 200)))
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
    ctx.setdefault("BLURB_STYLE", blurb_style or "sabre")
    ctx.setdefault("BLURB_WORDS", blurb_words or 200)

    # Output tokens
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
