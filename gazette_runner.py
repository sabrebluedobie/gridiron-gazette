# gazette_runner.py
import argparse, json, re, subprocess, sys
from datetime import date
from pathlib import Path
from typing import Dict, Any, List
from docxtpl import DocxTemplate
from gazette_data import fetch_week_from_espn, build_context

def _safe(s: str) -> str:
    import re as _re
    return _re.sub(r"[^A-Za-z0-9._-]+", "_", s or "")

def render_docx(context: Dict[str, Any], template="recap_template.docx", out_root="recaps") -> str:
    league = context.get("league", "League")
    day = context.get("date") or date.today().isoformat()
    week = _safe(context.get("week", "Week"))
    out_dir = Path(out_root) / _safe(league) / day
    out_dir.mkdir(parents=True, exist_ok=True)
    docx_path = out_dir / f"Gazette_{week}.docx"
    doc = DocxTemplate(template)
    doc.render(context)
    doc.save(str(docx_path))
    return str(docx_path)

def to_pdf(docx_path: str) -> str:
    pdf_path = str(Path(docx_path).with_suffix(".pdf"))
    # Try docx2pdf (Mac/Windows)
    try:
        from docx2pdf import convert
        convert(docx_path, pdf_path)
        return pdf_path
    except Exception:
        pass
    # Try LibreOffice (Linux/CI)
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
    out_docx = render_docx(ctx, template=args.template, out_root=args.out_dir)
    outputs = [out_docx]
    if args.pdf:
        pdf = to_pdf(out_docx)
        if pdf:
            outputs.append(pdf)
    return outputs

def main():
    ap = argparse.ArgumentParser(description="Gridiron Gazette (ESPN -> DOCX/PDF), single or multi.")
    ap.add_argument("--leagues", default="leagues.json")
    ap.add_argument("--template", default="recap_template.docx")
    ap.add_argument("--out-dir", default="recaps")
    ap.add_argument("--pdf", action="store_true")
    ap.add_argument("--multi", action="store_true")
    ap.add_argument("--league")
    ap.add_argument("--week", type=int)
    ap.add_argument("--week-label")
    ap.add_argument("--date")
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
