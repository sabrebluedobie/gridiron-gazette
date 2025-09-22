#!/usr/bin/env python3
# build_gazette.py — Gridiron Gazette production builder
# - DOCX render (docxtpl)
# - Stable diagonal gradient footer (table + inline image)
# - DOCX -> PDF (LibreOffice/headless)
# - PDF -> PDF/A-2b (Ghostscript; embeds/subsets fonts)
# - Optional lock (resilient if pikepdf missing)
# - JSON-driven logos for teams + league + sponsor

import argparse, sys, os, subprocess, shlex, logging, datetime as dt
import pathlib as pl
from typing import Dict, Any, List

from docxtpl import DocxTemplate, InlineImage
from docx import Document
from docx.shared import Mm

# local helpers you already have in repo
from assets_fix import (
    find_team_logo, find_league_logo, find_logo_by_name,
    debug_log_logo, validate_logo_map
)
from footer_gradient import add_footer_gradient
from gazette_data import assemble_context  # <-- ESPN data + context builder

# ---------------------- Configuration ----------------------
DEFAULT_TEMPLATE = "recap_template.docx"
DEFAULT_OUTDIR   = "recaps"
FOOTER_GRADIENT  = pl.Path("./logos/footer_gradient_diagonal.png")  # ensure this file exists

# ---------------------- CLI / weeks ------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--league-id", required=True)
    p.add_argument("--year", type=int, required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--week", type=int)
    g.add_argument("--auto-week", action="store_true")
    p.add_argument("--week-offset", type=int, default=0)
    p.add_argument("--template", default=DEFAULT_TEMPLATE)
    p.add_argument("--output-dir", default=DEFAULT_OUTDIR)
    p.add_argument("--llm-blurbs", action="store_true")
    p.add_argument("--blurb-style", default="sabre")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()

# --- replace the old compute_auto_week with this ---
def compute_fantasy_week(offset: int = 0) -> int:
    """
    Fantasy week = 1 + whole weeks since season start.
    Season start comes from env FANTASY_SEASON_START=YYYY-MM-DD (Tuesday works well),
    else we default to first Tuesday in September of the given YEAR if provided later.
    """
    import datetime as _dt

    # Prefer explicit env (lets you set different for each season)
    s = os.getenv("FANTASY_SEASON_START", "").strip()
    if s:
        season_start = _dt.date.fromisoformat(s)
    else:
        # fallback: first Tuesday in September of THIS YEAR
        today = _dt.date.today()
        y = today.year
        sept1 = _dt.date(y, 9, 1)
        # weekday(): Mon=0..Sun=6; we want Tue=1
        delta = (1 - sept1.weekday()) % 7
        season_start = sept1 + _dt.timedelta(days=delta)

    today = _dt.date.today()
    days = (today - season_start).days
    base_week = 1 if days < 0 else 1 + (days // 7)
    return max(1, base_week + offset)


# ---------------------- Converters -------------------------
def docx_to_pdf(docx_path: pl.Path, out_dir: pl.Path | None = None) -> pl.Path:
    docx = docx_path.resolve()
    outd = (out_dir or docx.parent).resolve()
    outd.mkdir(parents=True, exist_ok=True)
    cmd = (
        f'soffice --headless --nologo --nolockcheck '
        f'--convert-to pdf --outdir {shlex.quote(str(outd))} {shlex.quote(str(docx))}'
    )
    subprocess.run(cmd, shell=True, check=True)
    pdf_path = outd / (docx.stem + ".pdf")
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not created: {pdf_path}")
    return pdf_path

def pdf_to_pdfa(input_pdf: pl.Path, output_pdf: pl.Path) -> pl.Path:
    out = output_pdf.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = (
        "gs -dBATCH -dNOPAUSE -dNOOUTERSAVE "
        "-sDEVICE=pdfwrite "
        "-dPDFA=2 -dPDFACompatibilityPolicy=1 "
        "-dEmbedAllFonts=true -dSubsetFonts=true "
        "-dProcessColorModel=/DeviceRGB -dUseCIEColor "
        f"-sOutputFile={shlex.quote(str(out))} {shlex.quote(str(input_pdf))}"
    )
    subprocess.run(cmd, shell=True, check=True)
    if not out.exists():
        raise FileNotFoundError(f"PDF/A not created: {out}")
    return out

def lock_pdf_resilient(src: pl.Path, dst: pl.Path, owner: str = "owner-secret") -> pl.Path:
    """Try to lock with pikepdf; fallback to unlocked copy on any error."""
    try:
        from pikepdf import Pdf, Encryption, Permissions
        perms = Permissions(
            extract=False, modify_annotation=False, modify_form=False,
            modify_other=False, print_lowres=False, print_highres=False
        )
        with Pdf.open(str(src)) as pdf:
            pdf.save(str(dst), encryption=Encryption(owner=owner, user="", allow=perms))
        return dst
    except Exception as e:
        print(f"[lock_pdf] {e}; emitting UNLOCKED PDF/A")
        import shutil
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(src), str(dst))
        return dst

# ---------------------- Logo Injection ---------------------
def attach_logos(doc: DocxTemplate, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    JSON-first logo injection:
      - League logo from explicit LEAGUE_LOGO_PATH or JSON key "LEAGUE_LOGO",
        otherwise try LEAGUE_LOGO_NAME / LEAGUE_NAME through find_league_logo()
      - Sponsor from SPONSOR_LOGO_PATH or JSON key "SPONSOR_LOGO"
      - Home/Away and per-game team logos from *_TEAM_NAME
    """
    out = dict(ctx)

    # League logo (prefer explicit path)
    league_path = out.get("LEAGUE_LOGO_PATH")
    if league_path and pl.Path(league_path).exists():
        out["LEAGUE_LOGO"] = InlineImage(doc, league_path, width=Mm(26))
    else:
        # JSON key direct
        ll = find_logo_by_name("LEAGUE_LOGO")
        if ll.exists():
            out["LEAGUE_LOGO"] = InlineImage(doc, str(ll), width=Mm(26))
        else:
            # name-based resolver
            league_name = out.get("LEAGUE_LOGO_NAME") or out.get("LEAGUE_NAME")
            if league_name:
                debug_log_logo(league_name, kind="league")
                league_logo = find_league_logo(league_name)
                if league_logo.exists():
                    out["LEAGUE_LOGO"] = InlineImage(doc, str(league_logo), width=Mm(26))

    # Sponsor logo (prefer explicit path)
    sponsor_path = out.get("SPONSOR_LOGO_PATH")
    if sponsor_path and pl.Path(sponsor_path).exists():
        out["SPONSOR_LOGO"] = InlineImage(doc, sponsor_path, width=Mm(50))
    else:
        sl = find_logo_by_name("SPONSOR_LOGO")
        if sl.exists():
            out["SPONSOR_LOGO"] = InlineImage(doc, str(sl), width=Mm(50))

    # Single-match (top block)
    for side in ("HOME", "AWAY"):
        name_key = f"{side}_TEAM_NAME"
        if out.get(name_key):
            team_name = out[name_key]
            debug_log_logo(team_name, kind="team")
            logo_path = find_team_logo(team_name)
            out[f"{side}_LOGO"] = InlineImage(doc, str(logo_path), width=Mm(20))

    # Per-game entries
    for g in out.get("GAMES", []):
        hn = g.get("HOME_TEAM_NAME")
        an = g.get("AWAY_TEAM_NAME")
        if hn:
            debug_log_logo(hn, kind="team")
            g["HOME_LOGO"] = InlineImage(doc, str(find_team_logo(hn)), width=Mm(18))
        if an:
            debug_log_logo(an, kind="team")
            g["AWAY_LOGO"] = InlineImage(doc, str(find_team_logo(an)), width=Mm(18))
    return out

# ---------------------- Main -------------------------------
def _mask(s: str) -> str:
    return f"{len(s)} chars" if s else "MISSING"

def main():
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")
    week = args.week if not args.auto_week else compute_fantasy_week(args.week_offset)

    print("=== Build Configuration ===")
    print(f"Environment: {os.getenv('GITHUB_ENV', 'local') and 'actions' or 'local'}")
    print(f"Mode: single")
    print(f"Auto-week: {'true' if args.auto_week else 'false'}")
    print(f"LLM Blurbs: {args.llm_blurbs}")
    print(f"Blurb Style: {args.blurb_style}")
    print(f"Year: {args.year}")
    print(f"Week: {week}")
    print(f"Output: ./{args.output_dir}/")
    print()

    # Preflight: ESPN cookies presence (masked)
    s2 = os.getenv("ESPN_S2", "")
    swid = os.getenv("SWID", "")
    print(f"[preflight] ESPN_S2: {_mask(s2)}, SWID: {_mask(swid)}")

    # Validate template
    template_path = pl.Path(args.template)
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {args.template}")

    # Prepare output path
    out_dir = pl.Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    docx_path = out_dir / f"gazette_week_{week}.docx"

    if args.dry_run:
        print(f"[dry-run] Would build {docx_path}")
        sys.exit(0)

    # JSON logo map sanity
    missing = validate_logo_map()
    if missing:
        print(f"[logo] Warning: {missing} mapped logo(s) are missing on disk.")

    # 1) Build context from data (ESPN fetch inside gazette_data.py)
    ctx: Dict[str, Any] = assemble_context(
        league_id=args.league_id,
        year=args.year,
        week=week,
        llm_blurbs=args.llm_blurbs,
        blurb_style=args.blurb_style
    )

    # Optional explicit paths for league/sponsor
    # (uncomment and adjust if you want to force a specific file)
    # ctx["LEAGUE_LOGO_PATH"]  = "logos/team_logos/brownseakc.png"
    # ctx["SPONSOR_LOGO_PATH"] = "logos/team_logos/gazette_logo.png"

    # 2) Render DOCX
    doc = DocxTemplate(str(template_path))
    ctx = attach_logos(doc, ctx)  # inject InlineImage fields
    doc.render(ctx)
    doc.save(str(docx_path))
    print(f"Output DOCX: {docx_path}")

    # 3) Stable footer gradient (no floating shapes)
    if FOOTER_GRADIENT.exists():
        add_footer_gradient(docx_path, FOOTER_GRADIENT, bar_height_mm=12.0)
    else:
        print(f"[footer] Gradient image not found at {FOOTER_GRADIENT}, skipping footer overlay.")

    # 4) DOCX -> PDF, then PDF -> PDF/A-2b
    pdf_path = docx_to_pdf(docx_path)
    print(f"PDF: {pdf_path}")
    pdfa_tmp = pdf_path.with_suffix(".pdfa.pdf")
    pdfa_path = pdf_to_pdfa(pdf_path, pdfa_tmp)
    print(f"PDF/A: {pdfa_path}")

    # 5) Optional lock (resilient)
    locked = pdf_path.with_suffix(".locked.pdf")
    final_pdf = lock_pdf_resilient(pdfa_path, locked)

    # Replace the non-PDF/A with the PDF/A (locked or unlocked)
    try:
        pdf_path.unlink(missing_ok=True)  # 3.11+
    except TypeError:
        if pdf_path.exists():
            os.remove(str(pdf_path))
    final_pdf.rename(pdf_path)
    print(f"[build] Final PDF/A at: {pdf_path}")

    print("[build] SUCCESS")
    sys.exit(0)

if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        logging.exception("External tool failed: %s", e)
        sys.exit(2)
    except Exception as e:
        logging.exception("Error building gazette: %s", e)
        sys.exit(1)
