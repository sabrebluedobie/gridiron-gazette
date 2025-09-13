#!/usr/bin/env python3
"""
Generate styled Weekly Gazette DOCX/PDF files for one or many leagues.

- Reads leagues from --leagues (default: leagues.json)
- Pulls matchup data via gazette_data.fetch_week_from_espn
- Builds context via gazette_data.build_context
- Optionally expands blurbs & spotlight via LLM (JSON-only, player-validated)
- Adds per-slot (MATCHUPi_*) keys and InlineImage logos
- Renders with docxtpl and can convert to PDF via LibreOffice/docx2pdf

Examples:
  python3 gazette_runner.py --slots 10 --pdf
  python3 gazette_runner.py --league "My League" --week 1 --slots 8
  python3 gazette_runner.py --branding-test --print-logo-map --pdf
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 3rd party
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

# Local modules expected in this repo
try:
    from gazette_data import build_context, fetch_week_from_espn
except Exception as e:
    print("Error:  Unable to import gazette_data. Run from the repo root.", e, file=sys.stderr)
    raise

# --------------------------------------------------------------------------------------
# PDF helpers
# --------------------------------------------------------------------------------------

def to_pdf_with_soffice(docx_path: str) -> str:
    """Convert DOCX to PDF using LibreOffice. Returns the PDF path."""
    outdir = os.path.dirname(docx_path) or "."
    pdf_path = os.path.splitext(docx_path)[0] + ".pdf"
    cmd = ["soffice", "--headless", "--convert-to", "pdf", "--outdir", outdir, docx_path]
    try:
        subprocess.run(cmd, check=True)
    except Exception:
        # Homebrew app bundle path on macOS
        cmd[0] = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
        subprocess.run(cmd, check=True)
    return pdf_path


def to_pdf_with_docx2pdf(docx_path: str) -> str:
    """Convert with Word (Windows/macOS) via docx2pdf if available."""
    from docx2pdf import convert as _convert  # type: ignore
    pdf_path = os.path.splitext(docx_path)[0] + ".pdf"
    _convert(docx_path, pdf_path)
    return pdf_path


def to_pdf(docx_path: str, engine: str = "auto") -> str:
    """
    engine = auto|soffice|docx2pdf
    """
    if engine == "soffice":
        return to_pdf_with_soffice(docx_path)
    if engine == "docx2pdf":
        try:
            return to_pdf_with_docx2pdf(docx_path)
        except Exception:
            return to_pdf_with_soffice(docx_path)

    # auto
    try:
        return to_pdf_with_docx2pdf(docx_path)
    except Exception:
        return to_pdf_with_soffice(docx_path)

# --------------------------------------------------------------------------------------
# Logo helpers
# --------------------------------------------------------------------------------------

LOGO_DIRS = [
    "logos/generated_logos",
    "logos/generated_logo",     # singular (you mentioned this case)
    "logos/ai",
    "logos",
]

def _sanitize_name(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    base = re.sub(r"_+", "_", base)
    return base

def find_logo_path(name: str) -> Optional[str]:
    """Search known logo dirs for a PNG/JPG matching team/league/business name."""
    if not name:
        return None
    sanitized = _sanitize_name(name).lower()
    exts = [".png", ".jpg", ".jpeg", ".webp", ".bmp"]

    # exact filename first
    for d in LOGO_DIRS:
        base = Path(d)
        if not base.exists():
            continue
        for ext in exts:
            p = base / f"{sanitized}{ext}"
            if p.is_file():
                return str(p.resolve())

    # loose contains match
    candidates: List[Path] = []
    for d in LOGO_DIRS:
        base = Path(d)
        if not base.exists():
            continue
        for f in base.glob("*"):
            if f.is_file() and f.suffix.lower() in exts:
                if sanitized in f.stem.lower():
                    candidates.append(f.resolve())
    if candidates:
        return str(sorted(candidates, key=lambda p: len(p.name))[0])
    return None

def add_logo_images(context: Dict[str, Any], doc: DocxTemplate, max_slots: int, width_mm: int = 25,
                    logo_map: Optional[Dict[str, str]] = None) -> None:
    """Add MATCHUPi_HOME_LOGO / MATCHUPi_AWAY_LOGO InlineImages or a visible placeholder."""
    for i in range(1, max_slots + 1):
        home = context.get(f"MATCHUP{i}_HOME", "") or ""
        away = context.get(f"MATCHUP{i}_AWAY", "") or ""

        # home
        hp = find_logo_path(home) if home else None
        if hp and Path(hp).is_file():
            context[f"MATCHUP{i}_HOME_LOGO"] = InlineImage(doc, hp, width=Mm(width_mm))
            if logo_map is not None: logo_map[home] = hp
        else:
            context[f"MATCHUP{i}_HOME_LOGO"] = "[no-logo]"

        # away
        ap = find_logo_path(away) if away else None
        if ap and Path(ap).is_file():
            context[f"MATCHUP{i}_AWAY_LOGO"] = InlineImage(doc, ap, width=Mm(width_mm))
            if logo_map is not None: logo_map[away] = ap
        else:
            context[f"MATCHUP{i}_AWAY_LOGO"] = "[no-logo]"

def add_branding_images(context: Dict[str, Any], doc: DocxTemplate, league_cfg: Dict[str, Any], width_mm: int = 30) -> None:
    """Set LEAGUE_LOGO and BUSINESS_LOGO if found."""
    # League logo
    ll = league_cfg.get("league_logo") or find_logo_path(league_cfg.get("league_logo_name", "")) \
         or find_logo_path(league_cfg.get("name", "")) or find_logo_path("BrownSEA-KC")  # your known filename
    if ll and Path(ll).is_file():
        context["LEAGUE_LOGO"] = InlineImage(doc, ll, width=Mm(width_mm))
    else:
        context["LEAGUE_LOGO"] = "[no-logo]"

    # Business/footer logo (Gridiron Gazette)
    bl = league_cfg.get("business_logo") or find_logo_path("gazette_logo")
    if bl and Path(bl).is_file():
        context["BUSINESS_LOGO"] = InlineImage(doc, bl, width=Mm(width_mm))
    else:
        context["BUSINESS_LOGO"] = "[no-logo]"

# --------------------------------------------------------------------------------------
# Context mapping helpers
# --------------------------------------------------------------------------------------

def add_enumerated_matchups(context: Dict[str, Any], max_slots: int) -> None:
    """
    Expand context['games'] list into numbered keys the template uses.
    """
    games: List[Dict[str, Any]] = context.get("games", []) or []
    for i in range(1, max_slots + 1):
        g = games[i - 1] if i - 1 < len(games) else {}

        home = g.get("home", "") or ""
        away = g.get("away", "") or ""
        hs   = g.get("hs", "")
        aS   = g.get("as", "")  # dict key 'as' is fine; store to aS var

        blurb    = g.get("blurb", "") or ""
        top_home = g.get("top_home", "") or ""
        top_away = g.get("top_away", "") or ""
        bust     = g.get("bust", "") or ""
        keyplay  = g.get("keyplay", "") or ""
        dnote    = g.get("def", "") or ""

        context[f"MATCHUP{i}_HOME"] = home
        context[f"MATCHUP{i}_AWAY"] = away
        context[f"MATCHUP{i}_HS"]   = hs
        context[f"MATCHUP{i}_AS"]   = aS
        context[f"MATCHUP{i}_BLURB"] = blurb

        context[f"MATCHUP{i}_TOP_HOME"] = top_home
        context[f"MATCHUP{i}_TOP_AWAY"] = top_away
        context[f"MATCHUP{i}_BUST"]     = bust
        context[f"MATCHUP{i}_KEYPLAY"]  = keyplay
        context[f"MATCHUP{i}_DEF"]      = dnote

        # Compat/legacy fields some templates use
        try:
            hs_f = float(hs) if hs != "" else float("nan")
            as_f = float(aS) if aS != "" else float("nan")
            if hs != "" and aS != "":
                scoreline = f"{home} {hs} – {away} {aS}"
            else:
                scoreline = f"{home} vs {away}".strip()
            headline = f"{home if hs_f >= as_f else away} def. {away if hs_f >= as_f else home}"
        except Exception:
            scoreline = f"{home} vs {away}".strip()
            headline = scoreline

        context[f"MATCHUP{i}_TEAMS"]    = scoreline
        context[f"MATCHUP{i}_HEADLINE"] = headline
        context[f"MATCHUP{i}_BODY"]     = blurb

def add_template_synonyms(context: Dict[str, Any], slots: int) -> None:
    """
    Flatten award structures and add top-level aliases your Word template uses.
    """
    context["WEEK_NUMBER"] = context.get("week", "") or context.get("week_num", "")
    if "WEEKLY_INTRO" not in context:
        context["WEEKLY_INTRO"] = context.get("intro", "")

    awards = context.get("awards", {}) or {}
    top_score   = awards.get("top_score", {}) or {}
    low_score   = awards.get("low_score", {}) or {}
    largest_gap = awards.get("largest_gap", {}) or {}

    context["AWARD_TOP_TEAM"]      = top_score.get("team", "")
    context["AWARD_TOP_NOTE"]      = str(top_score.get("points", "")) or ""
    context["AWARD_CUPCAKE_TEAM"]  = low_score.get("team", "")
    context["AWARD_CUPCAKE_NOTE"]  = str(low_score.get("points", "")) or ""
    context["AWARD_KITTY_TEAM"]    = largest_gap.get("desc", "")
    context["AWARD_KITTY_NOTE"]    = str(largest_gap.get("gap", "")) or ""

# --------------------------------------------------------------------------------------
# Template inspection helper (safe across docxtpl versions)
# --------------------------------------------------------------------------------------

def _safe_get_missing(doc: DocxTemplate, ctx: Dict[str, Any]) -> List[str]:
    """
    Return template vars not present in ctx (best-effort; does not crash older docxtpl).
    """
    try:
        vars_in_tpl = set(doc.get_undeclared_template_variables())
        unknown = sorted([v for v in vars_in_tpl if v not in ctx])
        return unknown
    except Exception:
        return []

# --------------------------------------------------------------------------------------
# LLM blurb: JSON-first, player-validated
# --------------------------------------------------------------------------------------

import json as _json_mod
import re as _re_mod
from typing import Any as _Any, Dict as _Dict, List as _List

def _ad_as_dict(x: _Any) -> _Dict[str, _Any]:
    if isinstance(x, dict):
        return dict(x)
    try:
        return vars(x).copy()
    except Exception:
        d = {}
        for k in dir(x):
            if k.startswith("_"): continue
            v = getattr(x, k, None)
            if callable(v): continue
            d[k] = v
        return d

def _lineup_to_rows(lineup: _Any) -> _List[_Dict[str, _Any]]:
    rows: _List[_Dict[str, _Any]] = []
    for p in (list(lineup) if lineup else []):
        d = _ad_as_dict(p)
        name = d.get("name") or d.get("playerName") or d.get("fullName") or ""
        pts  = d.get("points") or d.get("applied_total") or d.get("totalPoints") or 0
        proj = d.get("projected_points") or d.get("projected_total") or 0
        slot = d.get("slot_position") or d.get("position") or ""
        try: pts = float(pts)
        except Exception: pts = 0.0
        try: proj = float(proj)
        except Exception: proj = 0.0
        if name:
            rows.append({"name": name, "pts": pts, "proj": proj, "slot": slot})
    rows.sort(key=lambda r: r["pts"], reverse=True)
    return rows

def _collect_players_for_week(league_id: int, year: int, espn_s2: str, swid: str, week: Optional[int]) -> Dict[tuple, Dict[str, Any]]:
    """ {(home, away): {"home_players":[...], "away_players":[...]}} """
    try:
        from espn_api.football import League
    except Exception:
        return {}
    lg = League(league_id=league_id, year=year, espn_s2=espn_s2 or None, swid=swid or None)
    boxes = getattr(lg, "box_scores", None)
    box_list = lg.box_scores(week=week) if callable(boxes) else lg.box_score(week=week)  # type: ignore[attr-defined]

    out: Dict[tuple, Dict[str, Any]] = {}
    for b in box_list:
        bd = _ad_as_dict(b)
        ht = _ad_as_dict(bd.get("home_team"))
        at = _ad_as_dict(bd.get("away_team"))
        hname = ht.get("team_name") or ht.get("name") or ""
        aname = at.get("team_name") or at.get("name") or ""
        hl = bd.get("home_lineup") or bd.get("homeLineup") or []
        al = bd.get("away_lineup") or bd.get("awayLineup") or []
        out[(hname, aname)] = {
            "home": hname, "away": aname,
            "home_players": _lineup_to_rows(hl),
            "away_players": _lineup_to_rows(al),
        }
    return out

def _top_and_bust(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    top = rows[0] if rows else {"name": "", "pts": 0}
    starters = [r for r in rows if r.get("proj", 0) > 0]
    pool = starters if starters else rows
    bust = (sorted(pool, key=lambda r: r["pts"])[0] if pool else {"name": "", "pts": 0})
    return {"top": top, "bust": bust}

def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = _re_mod.search(r"\{.*\}", text, flags=_re_mod.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None

BLURB_JSON_PROMPT = """You are a careful fantasy football recap writer.

Rules (strict):
- Use ONLY the players and stats provided; do NOT invent players or stats.
- Names must be EXACTLY one of: {allowed_names_list}. If a name isn't in that list, use "" (empty).
- Keep the blurb concise and vivid. No emojis.
- Output ONLY a single JSON object with this schema:
  {{
    "blurb": string,               # ~{words} words
    "key_play": string,            # 1 sentence, no fabricated yardages
    "top_home": string,            # player name from allowed list, or ""
    "top_away": string,            # player name from allowed list, or ""
    "bust": string,                # player name from allowed list, or ""
    "defense_note": string         # short note, or ""
  }}

Context:
Week: {week}
Home: {home} ({hs})
Away: {away} ({as})

Home players (JSON): {home_players_json}
Away players (JSON): {away_players_json}

Style hint: {style_hint}
"""

_STYLE_VARIANTS = [
    "straight newsroom tone, active verbs",
    "analyst tone with efficiency and key moments",
    "radio call tone—short, energetic sentences",
    "color commentator tone with rhythm and punchy phrasing",
]

def maybe_expand_blurbs_json(
    ctx: Dict[str, Any],
    *,
    words: int = 150,
    model: str = "gpt-4o-mini",
    temperature: float = 0.4,
    league_id: Optional[int] = None,
    year: Optional[int] = None,
    espn_s2: str = "",
    swid: str = "",
    week: Optional[int] = None,
    blurb_style: Optional[str] = None,
) -> None:
    """Populate each game's blurb + spotlight fields from JSON returned by the model."""
    try:
        from openai import OpenAI
        client = OpenAI()
    except Exception:
        return  # no client, skip

    games: List[Dict[str, Any]] = ctx.get("games", []) or []
    players_map: Dict[tuple, Dict[str, Any]] = {}

    if league_id and year:
        try:
            players_map = _collect_players_for_week(league_id, year, espn_s2, swid, week)
        except Exception:
            players_map = {}

    week_label = ctx.get("week") or ctx.get("week_num") or ""

    for i, g in enumerate(games):
        home = g.get("home", "") or ""
        away = g.get("away", "") or ""
        hs   = g.get("hs", "")
        aS   = g.get("as", "")

        # Find matching sheet
        sheet = players_map.get((home, away))
        if not sheet and players_map:
            for (h, a), s in players_map.items():
                if (h.lower() in home.lower() or home.lower() in h.lower()) and \
                   (a.lower() in away.lower() or away.lower() in a.lower()):
                    sheet = s; break

        home_rows = (sheet or {}).get("home_players", [])
        away_rows = (sheet or {}).get("away_players", [])

        allowed = sorted({r["name"] for r in home_rows + away_rows if r.get("name")})
        allowed_str = ", ".join(allowed) if allowed else "(none)"

        htb = _top_and_bust(home_rows)
        atb = _top_and_bust(away_rows)

        # vary style a bit; allow explicit override
        style_hint = blurb_style or _STYLE_VARIANTS[i % len(_STYLE_VARIANTS)]
        prompt = BLURB_JSON_PROMPT.format(
            week=week_label,
            home=home, hs=hs if hs != "" else "–",
            away=away, aS=aS if aS != "" else "–",
            home_players_json=json.dumps(home_rows, ensure_ascii=False),
            away_players_json=json.dumps(away_rows, ensure_ascii=False),
            words=int(words),
            style_hint=style_hint,
            allowed_names_list=allowed_str,
        )

        content: Optional[str] = None
        try:
            # Prefer structured JSON if supported
            resp = client.chat.completions.create(
                model=model,
                temperature=temperature,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "Return ONLY valid JSON. Use only provided players/stats."},
                    {"role": "user", "content": prompt},
                ],
            )
            content = (resp.choices[0].message.content or "").strip()
        except Exception:
            # Fallback
            resp = client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": "Return ONLY valid JSON. Use only provided players/stats."},
                    {"role": "user", "content": prompt},
                ],
            )
            content = (resp.choices[0].message.content or "").strip()

        try:
            data = _extract_json(content or "") or {}
        except Exception:
            data = {}

        def _fix_name(n: str) -> str:
            return n if n in allowed else ""

        blurb   = (data.get("blurb") or "").strip()
        keyplay = (data.get("key_play") or "").strip()
        top_home = _fix_name((data.get("top_home") or "").strip())
        top_away = _fix_name((data.get("top_away") or "").strip())
        bust     = _fix_name((data.get("bust") or "").strip())
        dnote    = (data.get("defense_note") or "").strip()

        # Fallbacks from stats we trust
        if not top_home and htb["top"].get("name"):
            top_home = f"{htb['top']['name']} ({htb['top'].get('pts',0):.1f})"
        if not top_away and atb["top"].get("name"):
            top_away = f"{atb['top']['name']} ({atb['top'].get('pts',0):.1f})"
        if not bust:
            bust = htb["bust"].get("name") or atb["bust"].get("name") or ""

        # Avoid unicode issues seen earlier
        blurb = blurb.replace("…", "...").replace("\u2013", "–")
        keyplay = keyplay.replace("…", "...").replace("\u2013", "–")

        # Write back for enumerator
        if blurb: g["blurb"] = blurb
        g["keyplay"] = keyplay
        g["top_home"] = top_home
        g["top_away"] = top_away
        g["bust"] = bust
        g["def"] = dnote

# --------------------------------------------------------------------------------------
# Utility
# --------------------------------------------------------------------------------------

def safe_title(s: str) -> str:
    s = re.sub(r"[^\w\s\-\(\)\._]", "_", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s

# --------------------------------------------------------------------------------------
# Renderers
# --------------------------------------------------------------------------------------

def render_single_league(cfg: Dict[str, Any], args: argparse.Namespace) -> Tuple[str, Optional[str], Dict[str, str]]:
    """
    Render one league's gazette. Returns (docx_path, pdf_path_or_None, logo_map).
    """
    league_id = cfg.get("league_id")
    year = cfg.get("year")
    espn_s2 = cfg.get("espn_s2", "")
    swid = cfg.get("swid", "")

    # Fetch week data; support either signature
    try:
        games = fetch_week_from_espn(league_id, year, espn_s2, swid, args.week)
    except TypeError:
        games = fetch_week_from_espn(league_id, year, espn_s2, swid)

    ctx = build_context(cfg, games)

    # Optional labels
    if args.week is not None:
        ctx["week_num"] = args.week
    if args.week_label:
        ctx["week"] = args.week_label
    if args.date:
        ctx["date"] = args.date

    # Provide a title if your template uses {{title}}
    if "title" not in ctx:
        wk = ctx.get("week") or ctx.get("week_num") or ""
        ctx["title"] = f"Gridiron Gazette — Week {wk}" if wk else "Gridiron Gazette"

    # Expand blurbs first (writes into ctx['games'][i])
    if args.llm_blurbs:
        try:
            maybe_expand_blurbs_json(
                ctx,
                words=args.blurb_words,
                model=args.model,
                temperature=args.temperature,
                league_id=league_id, year=year,
                espn_s2=espn_s2, swid=swid, week=args.week,
                blurb_style=args.blurb_style,
            )
        except Exception as e:
            print(f"[warn] LLM blurbs skipped: {e}")

    # Then flatten into MATCHUPi_* keys
    add_enumerated_matchups(ctx, max_slots=args.slots)

    doc = DocxTemplate(args.template)

    # Branding (header/footer logos)
    add_branding_images(ctx, doc, cfg, width_mm=max(20, min(args.logo_mm, 60)))

    # Team logos per matchup
    logo_map: Dict[str, str] = {}
    add_logo_images(ctx, doc, max_slots=args.slots, width_mm=args.logo_mm, logo_map=logo_map)

    # Synonyms / awards mapping
    add_template_synonyms(ctx, slots=args.slots)

    # Helpful warning about unknown variables
    unknown = _safe_get_missing(doc, ctx)
    if unknown:
        print(f"[warn] Template references unknown variables: {unknown}")

    # Output paths
    league_name = cfg.get("name", f"league_{league_id}") or f"league_{league_id}"
    out_dir = Path(args.out_dir) / safe_title(league_name)
    out_dir.mkdir(parents=True, exist_ok=True)

    week_label = ctx.get("week", f"Week_{ctx.get('week_num','')}")
    date_label = ctx.get("date", "")
    base = safe_title(f"Gazette_{week_label}_{date_label}") if date_label else safe_title(f"Gazette_{week_label}")

    docx_path = out_dir / f"{base}.docx"
    doc.render(ctx)
    doc.save(str(docx_path))

    pdf_path: Optional[str] = None
    if args.pdf:
        try:
            pdf_path = to_pdf(str(docx_path), engine=args.pdf_engine)
        except Exception as e:
            print(f"[warn] PDF export failed ({e}). DOCX created.", file=sys.stderr)
            pdf_path = None

    if args.print_logo_map:
        print(f"[logo-map] {league_name}:")
        for team, path in sorted(logo_map.items()):
            print(f"  - {team} -> {path}")

    return str(docx_path), pdf_path, logo_map


def render_branding_test(cfg: Dict[str, Any], args: argparse.Namespace) -> Tuple[str, Optional[str], Dict[str, str]]:
    """
    Minimal render to verify headers/footers/logos and template wiring.
    """
    ctx: Dict[str, Any] = {
        "week": args.week_label or f"Branding Test",
        "date": args.date or "",
        "title": "Gridiron Gazette — Branding Test",
        "WEEKLY_INTRO": "Quick branding check: header, footer, and team logos.",
        "games": [
            {"home": "Nana's Hawks", "away": "Phoenix Blues", "hs": "", "as": "", "blurb": "Branding test matchup."}
        ],
    }

    # enumerate later after logos if you want; but either order is fine here
    add_enumerated_matchups(ctx, max_slots=max(1, args.slots))

    doc = DocxTemplate(args.template)
    add_branding_images(ctx, doc, cfg, width_mm=max(20, min(args.logo_mm, 60)))
    logo_map: Dict[str, str] = {}
    add_logo_images(ctx, doc, max_slots=max(1, args.slots), width_mm=args.logo_mm, logo_map=logo_map)
    add_template_synonyms(ctx, slots=max(1, args.slots))

    unknown = _safe_get_missing(doc, ctx)
    if unknown:
        print(f"[warn] Template references unknown variables: {unknown}")

    league_name = cfg.get("name", f"league_{cfg.get('league_id','')}") or "league"
    out_dir = Path(args.out_dir) / safe_title(league_name)
    out_dir.mkdir(parents=True, exist_ok=True)

    docx_path = out_dir / "Gazette_Branding_Test.docx"
    doc.render(ctx)
    doc.save(str(docx_path))

    pdf_path: Optional[str] = None
    if args.pdf:
        try:
            pdf_path = to_pdf(str(docx_path), engine=args.pdf_engine)
        except Exception as e:
            print(f"[warn] PDF export failed ({e}). DOCX created.", file=sys.stderr)
            pdf_path = None

    if args.print_logo_map:
        print(f"[logo-map] {league_name}:")
        for team, path in sorted(logo_map.items()):
            print(f"  - {team} -> {path}")

    return str(docx_path), pdf_path, logo_map

# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", default="leagues.json", help="Path to leagues config JSON.")
    ap.add_argument("--template", default="recap_template.docx", help="DOCX template to render.")
    ap.add_argument("--out-dir", default="recaps", help="Output root directory.")
    ap.add_argument("--pdf", action="store_true", help="Also export PDF.")
    ap.add_argument("--pdf-engine", default="auto", choices=["auto","soffice","docx2pdf"], help="PDF converter.")
    ap.add_argument("--league", default=None, help="Only render the league with this name.")
    ap.add_argument("--week", type=int, default=None, help="Force a specific completed week number.")
    ap.add_argument("--week-label", default=None, help='Override week label text, e.g. "Week 1 (Sep 4–9, 2025)".')
    ap.add_argument("--date", default=None, help="Override date label text.")
    ap.add_argument("--slots", type=int, default=10, help="Max matchup slots to render.")
    ap.add_argument("--logo-mm", type=int, default=25, help="Logo width in millimeters.")
    ap.add_argument("--print-logo-map", action="store_true", help="Print which logo file each team used.")
    ap.add_argument("--branding-test", action="store_true", help="Render a one-page branding smoke test.")
    ap.add_argument("--blurb-test", action="store_true", help="Quick test mode for LLM blurbs: uses sensible defaults and skips PDF unless --pdf is passed.")

    # LLM blurb options
    ap.add_argument("--llm-blurbs", action="store_true", help="Use LLM to expand blurbs & spotlight fields.")
    ap.add_argument("--blurb-words", type=int, default=150, help="Approx words for generated blurbs.")
    ap.add_argument("--model", default="gpt-4o-mini", help="OpenAI chat model.")
    ap.add_argument("--temperature", type=float, default=0.4, help="Creativity.")
    ap.add_argument("--blurb-style", default=None, help="Optional style hint (e.g. 'mascot').")

    return ap.parse_args()

# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------

def _apply_blurb_test_presets(args):
    """Apply safe, quick defaults when --blurb-test is set. No effect otherwise."""
    if not getattr(args, "blurb_test", False):
        return args

    # Friendly defaults only if not already provided
    if getattr(args, "week", None) in (None, ""):
        args.week = 1
    if getattr(args, "slots", None) in (None, 0):
        args.slots = 10

    # Ensure blurbs are on in test mode
    if not getattr(args, "llm_blurbs", False):
        args.llm_blurbs = True

    # Nudge defaults if user didn’t specify
    if not getattr(args, "blurb_words", None):
        args.blurb_words = 1000
    if not getattr(args, "model", None):
        args.model = "gpt-4o-mini"
    if not getattr(args, "temperature", None):
        args.temperature = 0.4
    if hasattr(args, "blurb_style") and not getattr(args, "blurb_style", None):
        args.blurb_style = "rtg"

    # Keep PDF OFF unless user explicitly passed --pdf
    # (Most fast-iterating on Mac hits converter issues; this avoids that surprise.)
    if not getattr(args, "pdf", False):
        args.pdf = False

    # Optional: quick console note so it’s obvious in logs
    print("[blurb-test] Using quick presets (week={}, slots={}, words={}, model={}, temp={}, style={}, pdf={})".format(
        args.week, args.slots, args.blurb_words, args.model, args.temperature,
        getattr(args, "blurb_style", None), args.pdf
    ))
    return args

def main() -> None:
    args = parse_args()
    args = _apply_blurb_test_presets(args)

    # Remove unexpected indentation below
    leagues_path = Path(args.leagues)
    if not leagues_path.exists():
        print(f"[error] Leagues file not found: {leagues_path}", file=sys.stderr)
        sys.exit(1)

    try:
        leagues: List[Dict[str, Any]] = json.loads(leagues_path.read_text())
    except Exception as e:
        print(f"[error] Failed to read {leagues_path}: {e}", file=sys.stderr)
        sys.exit(1)

    items = [l for l in leagues if not args.league or l.get("name") == args.league]
    if not items:
        print("[warn] No leagues matched the filter; nothing to do.")
        sys.exit(0)

    for cfg in items:
        if args.branding_test:
            docx_path, pdf_path, _ = render_branding_test(cfg, args)
        else:
            docx_path, pdf_path, _ = render_single_league(cfg, args)

        print(f"[ok] Wrote DOCX: {Path(docx_path).resolve()}")
        if pdf_path:
            print(f"[ok] Wrote PDF:  {Path(pdf_path).resolve()}")

if __name__ == "__main__":
    main()
