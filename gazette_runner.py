# gazette_runner.py
# ESPN -> context -> DOCX/PDF with enumerated MATCHUPi_* keys and optional logos.

import argparse, json, re, subprocess, sys
from datetime import date
from pathlib import Path
from typing import Dict, Any, List

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

from gazette_data import fetch_week_from_espn, build_context
from mascots_util import logo_for

# Try docx2pdf if available (Mac/Windows with Word); fall back to LibreOffice
try:
    from docx2pdf import convert  # type: ignore[import-not-found]
except Exception:
    convert = None  # we'll handle fallback gracefully

def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s or "")

def _as_str(v):
    try:
        f = float(v)
        return f"{int(f)}" if f.is_integer() else f"{f:.1f}"
    except Exception:
        return f"{v}" if v is not None else ""

def add_enumerated_matchups(context: Dict[str, Any], max_slots: int = 12) -> None:
    games = context.get("games", []) or []
    for i in range(1, max_slots + 1):
        g = games[i - 1] if i - 1 < len(games) else {}
        context[f"MATCHUP{i}_HOME"] = g.get("home", "") or ""
        context[f"MATCHUP{i}_AWAY"] = g.get("away", "") or ""
        context[f"MATCHUP{i}_HS"]   = _as_str(g.get("hs", ""))
        context[f"MATCHUP{i}_AS"]   = _as_str(g.get("as", ""))
        context[f"MATCHUP{i}_HOME_NAME"] = context[f"MATCHUP{i}_HOME"]
        context[f"MATCHUP{i}_AWAY_NAME"] = context[f"MATCHUP{i}_AWAY"]
        context[f"MATCHUP{i}_HOME_MASCOT"] = g.get("home_mascot", "") or ""
        context[f"MATCHUP{i}_AWAY_MASCOT"] = g.get("away_mascot", "") or ""
        context[f"MATCHUP{i}_TOP_HOME"]    = g.get("home_top", "") or ""
        context[f"MATCHUP{i}_TOP_AWAY"]    = g.get("away_top", "") or ""
        context[f"MATCHUP{i}_BUST"]        = g.get("biggest_bust", "") or ""
        context[f"MATCHUP{i}_KEYPLAY"]     = g.get("key_play", "") or ""
        context[f"MATCHUP{i}_DEF"]         = g.get("defense_note", "") or ""
        context[f"MATCHUP{i}_BLURB"]       = g.get("blurb", "") or ""

def add_logo_images(context: Dict[str, Any], doc: DocxTemplate, max_slots: int = 12, width_mm: float = 18.0) -> None:
    for i in range(1, max_slots + 1):
        home = context.get(f"MATCHUP{i}_HOME", "")
        away = context.get(f"MATCHUP{i}_AWAY", "")
        hp = logo_for(home)
        ap = logo_for(away)
        context[f"MATCHUP{i}_HOME_LOGO"] = InlineImage(doc, hp, width=Mm(width_mm)) if hp else ""
        context[f"MATCHUP{i}_AWAY_LOGO"] = InlineImage(doc, ap, width=Mm(width_mm)) if ap else ""

def render_docx(context: Dict[str, Any], template="recap_template.docx",
                out_root="recaps", slots: int = 12, logo_mm: float = 18.0) -> str:
    add_enumerated_matchups(context, max_slots=slots)

    league = context.get("league", "League")
    day = context.get("date") or date.today().isoformat()
    week = _safe(context.get("week", "Week"))
    out_dir = Path(out_root) / _safe(league) / day
    out_dir.mkdir(parents=True, exist_ok=True)

    docx_path = out_dir / f"Gazette_{week}.docx"
    doc = DocxTemplate(template)
    add_logo_images(context, doc, max_slots=slots, width_mm=logo_mm)
    doc.render(context)
    doc.save(str(docx_path))
    return str(docx_path)

def to_pdf(docx_path: str) -> str:
    pdf_path = str(Path(docx_path).with_suffix(".pdf"))
    # Try docx2pdf first
    if convert is not None:
        try:
            convert(docx_path, pdf_path)
            return pdf_path
        except Exception:
            pass
    # Fallback to LibreOffice headless (Linux/CI)
    try:
        outdir = str(Path(pdf_path).parent)
        subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", "--outdir", outdir, docx_path],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return pdf_path
    except Exception:
        print("[warn] PDF export skipped (no docx2pdf or soffice).")
        return ""

def run_single(cfg: Dict[str, Any], args) -> List[str]:
    games = fetch_week_from_espn(
        league_id=cfg["league_id"], year=cfg["year"],
        ***REMOVED***
        week=args.week
    )
    if not games:
        print(f"[warn] No games returned for {cfg.get('name')} (week={args.week or 'current'}). "
              f"If private, ensure espn_s2/SWID cookies in leagues.json.")
    ctx = build_context(cfg, games)
    if args.week_label:
        ctx["week"] = args.week_label
        ctx["title"] = f'{ctx["league"]} — {args.week_label}'
    if args.date:
        ctx["date"] = args.date

    out_docx = render_docx(ctx, template=args.template, out_root=args.out_dir,
                           slots=args.slots, logo_mm=args.logo_mm)
    outputs = [out_docx]
    if args.pdf:
        pdf = to_pdf(out_docx)
        if pdf:
            outputs.append(pdf)
    return outputs

def main():
    ap = argparse.ArgumentParser(description="Gridiron Gazette (ESPN -> DOCX/PDF), single or multi, enumerated placeholders.")
    ap.add_argument("--leagues", default="leagues.json")
    ap.add_argument("--template", default="recap_template.docx")
    ap.add_argument("--out-dir", default="recaps")
    ap.add_argument("--pdf", action="store_true", help="Also export PDF")
    ap.add_argument("--multi", action="store_true", help="Process all leagues in leagues.json")
    ap.add_argument("--league", help="Run only this league by name")
    ap.add_argument("--week", type=int, help="Override ESPN week (default: current)")
    ap.add_argument("--week-label", help='Visible label, e.g. "Week 1 (Sep 13–15, 2025)"')
    ap.add_argument("--date", help='Folder date (default: today, e.g., "2025-09-15")')
    ap.add_argument("--slots", type=int, default=12, help="How many MATCHUPi_* slots exist in the template")
    ap.add_argument("--logo-mm", type=float, default=18.0, help="Logo width (mm) for InlineImage")
    args = ap.parse_args()

    try:
        with open(args.leagues, "r") as f:
            leagues = json.load(f)
    except Exception as e:
        sys.exit(f"Failed to load {args.leagues}: {e}")

    outputs: List[str] = []
    if args.league:
        cfg = next((x for x in leagues if x.get("name") == args.league), None)
        if not cfg:
            names = ", ".join(x.get("name", "?") for x in leagues)
            sys.exit(f'No league named "{args.league}" in {args.leagues}. Known: {names}')
        outputs += run_single(cfg, args)
    else:
        items = leagues if args.multi else leagues[:1]
        for cfg in items:
            outputs += run_single(cfg, args)

    print("\nGenerated files:")
    for p in outputs:
        print(" •", p)

if __name__ == "__main__":
    main()
