#!/usr/bin/env python3
from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict

from docx import Document
from docx.text.paragraph import Paragraph

import gazette_data
from storymaker import StoryMaker, MatchupData, PlayerStat

# Optional OpenAI wrapper (safe if absent)
try:
    from llm_openai import chat as openai_llm
except Exception:
    openai_llm = None


def build_weekly_recap(
    league_id: int,
    year: int,
    week: int,
    template: str = "recap_template.docx",
    output_path: str = "recaps/Gazette_{year}_W{week02}.docx",
    use_llm_blurbs: bool = True,
) -> str:
    """
    Builds the Gazette docx by:
      1) fetching ESPN context (fills ALL template tokens),
      2) generating Sabre recaps into MATCHUP{i}_BLURB,
      3) rendering {{ TOKEN }} placeholders.
    """
    ctx = gazette_data.build_context(league_id, year, week)

    if use_llm_blurbs:
        _attach_sabre_recaps(ctx)
    else:
        _attach_simple_blurbs(ctx)

    # Render the doc
    out = _render_docx(template, output_path, ctx)
    return out


def _attach_sabre_recaps(ctx: Dict[str, Any]) -> None:
    maker = StoryMaker(llm=openai_llm if os.getenv("OPENAI_API_KEY") else None)

    count = int(ctx.get("MATCHUP_COUNT") or 7)
    league_name = str(ctx.get("LEAGUE_NAME", "League"))
    week_num = int(ctx.get("WEEK_NUMBER", 0) or 0)

    for i in range(1, min(count, 7) + 1):
        h = ctx.get(f"MATCHUP{i}_HOME"); a = ctx.get(f"MATCHUP{i}_AWAY")
        hs = ctx.get(f"MATCHUP{i}_HS");  as_ = ctx.get(f"MATCHUP{i}_AS")
        if not (h and a):
            continue

        # Grow optional “top performers” for extra flavor
        tops = []
        th = _safe(ctx.get(f"MATCHUP{i}_TOP_HOME", ""))
        ta = _safe(ctx.get(f"MATCHUP{i}_TOP_AWAY", ""))
        if th:
            tops.append(PlayerStat(name=th))
        if ta:
            tops.append(PlayerStat(name=ta))

        try:
            sa = float(str(hs)) if hs not in (None, "") else 0.0
            sb = float(str(as_)) if as_ not in (None, "") else 0.0
        except Exception:
            sa, sb = 0.0, 0.0

        md = MatchupData(
            league_name=league_name,
            week=week_num,
            team_a=str(h), team_b=str(a),
            score_a=sa, score_b=sb,
            top_performers=tops,
            winner=str(h) if sa >= sb else str(a),
            margin=abs(sa - sb),
        )
        ctx[f"MATCHUP{i}_BLURB"] = maker.generate_recap(md)  # 200–250 words, multi-paragraph + 🐾 signoff


def _attach_simple_blurbs(ctx: Dict[str, Any]) -> None:
    count = int(ctx.get("MATCHUP_COUNT") or 7)
    for i in range(1, min(count, 7) + 1):
        if ctx.get(f"MATCHUP{i}_BLURB"):
            continue
        h = ctx.get(f"MATCHUP{i}_HOME"); a = ctx.get(f"MATCHUP{i}_AWAY")
        hs = ctx.get(f"MATCHUP{i}_HS");  as_ = ctx.get(f"MATCHUP{i}_AS")
        if not (h and a):
            continue
        try:
            sa = float(str(hs)) if hs not in (None, "") else 0.0
            sb = float(str(as_)) if as_ not in (None, "") else 0.0
        except Exception:
            sa, sb = 0.0, 0.0
        winner = h if sa >= sb else a
        loser = a if winner == h else h
        margin = abs(sa - sb)
        tone = "nail-biter" if margin < 5 else ("statement win" if margin > 20 else "solid win")
        ctx[f"MATCHUP{i}_BLURB"] = f"{winner} topped {loser} {hs}-{as_} in a {tone}.\n\n—Sabre, your hilariously snarky 4-legged Gridiron Gazette reporter 🐾"


def _render_docx(template_path: str, out_pattern: str, ctx: Dict[str, Any]) -> str:
    tpl = Path(template_path)
    if not tpl.exists():
        raise FileNotFoundError(f"Template not found: {tpl}")

    week = int(ctx.get("WEEK_NUMBER", 0) or 0)
    out_path = out_pattern.format(year=ctx.get("YEAR", ""), week=week, week02=f"{week:02d}")
    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    doc = Document(str(tpl))
    replacements = {f"{{{{ {k} }}}}": str(v) for k, v in ctx.items()}
    _replace_in_document(doc, replacements)
    doc.save(str(out_file))
    return str(out_file)


def _replace_in_document(doc: Document, replacements: Dict[str, str]) -> None:
    def replace_in_paragraph(p: Paragraph) -> None:
        if not p.runs:
            return
        text = "".join(run.text for run in p.runs)
        orig = text
        for k, v in replacements.items():
            if k in text:
                text = text.replace(k, v)
        if text != orig:
            while p.runs:
                p.runs[0].clear()
                p.runs[0].text = ""
                p._element.remove(p.runs[0]._element)
            p.add_run(text)

    for p in doc.paragraphs:
        replace_in_paragraph(p)
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    replace_in_paragraph(p)


def _safe(s: Any) -> str:
    return "" if s is None else str(s)
