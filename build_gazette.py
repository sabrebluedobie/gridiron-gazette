#!/usr/bin/env python3
"""
build_gazette.py - FINAL PRODUCTION VERSION

Complete compatibility with weekly_recap.py and GitHub Actions
Enhanced logo handling for Unicode team names
Multi-league support via team_logos.json
Production-ready PDF generation pipeline
"""

import argparse, sys, os, subprocess, shlex, logging, datetime as dt
import pathlib as pl
from typing import Dict, Any, List

from docxtpl import DocxTemplate, InlineImage
from docx import Document
from docx.shared import Mm

# Import our comprehensive data fetching
from gazette_data import assemble_context

# Import existing helpers
from assets_fix import (
    find_team_logo, find_league_logo, find_logo_by_name,
    debug_log_logo, validate_logo_map
)
from footer_gradient import add_footer_gradient

# ---------------------- Configuration ----------------------
DEFAULT_TEMPLATE = "recap_template.docx"
DEFAULT_OUTDIR = "recaps"
FOOTER_GRADIENT = pl.Path("./logos/footer_gradient_diagonal.png")

# ---------------------- CLI Arguments ----------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    
    # Core arguments (required)
    p.add_argument("--league-id", required=True)
    p.add_argument("--year", type=int, required=True)
    
    # Week selection (one required)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--week", type=int)
    g.add_argument("--auto-week", action="store_true")
    
    # Optional arguments with defaults
    p.add_argument("--week-offset", type=int, default=0)
    p.add_argument("--template", default=DEFAULT_TEMPLATE)
    p.add_argument("--output-dir", default=DEFAULT_OUTDIR)
    
    # LLM options
    p.add_argument("--llm-blurbs", action="store_true")
    p.add_argument("--blurb-style", default="sabre")
    p.add_argument("--blurb-words", type=int, default=300)  # Added for compatibility
    
    # Control options
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verbose", action="store_true")
    
    return p.parse_args()

def compute_fantasy_week(offset: int = 0) -> int:
    """
    Compute current fantasy week with offset
    Compatible with existing weekly_recap.py logic
    """
    import datetime as _dt
    
    # Try environment variable first
    s = os.getenv("FANTASY_SEASON_START", "").strip()
    if s:
        try:
            season_start = _dt.date.fromisoformat(s)
        except:
            season_start = None
    else:
        season_start = None
    
    if not season_start:
        # Fallback: first Tuesday in September
        today = _dt.date.today()
        y = today.year
        sept1 = _dt.date(y, 9, 1)
        delta = (1 - sept1.weekday()) % 7
        season_start = sept1 + _dt.timedelta(days=delta)
    
    today = _dt.date.today()
    days = (today - season_start).days
    base_week = 1 if days < 0 else 1 + (days // 7)
    return max(1, base_week + offset)

# ---------------------- PDF Conversion ----------------------
def docx_to_pdf(docx_path: pl.Path, out_dir: pl.Path | None = None) -> pl.Path:
    """Convert DOCX to PDF using LibreOffice"""
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
    """Convert PDF to PDF/A using Ghostscript"""
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
    """Try to lock PDF with pikepdf; fallback to copy on error"""
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

# ---------------------- Enhanced Logo Integration ----------------------
def attach_logos(doc: DocxTemplate, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enhanced logo attachment with proper Unicode handling
    Uses team_logos.json as source of truth for multi-league support
    """
    out = dict(ctx)
    
    # League logo
    league_path = out.get("LEAGUE_LOGO_PATH")
    if league_path and pl.Path(league_path).exists():
        out["LEAGUE_LOGO"] = InlineImage(doc, league_path, width=Mm(26))
    else:
        # Try JSON mapping first
        ll = find_logo_by_name("LEAGUE_LOGO")
        if ll.exists():
            out["LEAGUE_LOGO"] = InlineImage(doc, str(ll), width=Mm(26))
        else:
            # Name-based resolver
            league_name = out.get("LEAGUE_LOGO_NAME") or out.get("LEAGUE_NAME")
            if league_name:
                debug_log_logo(league_name, kind="league")
                league_logo = find_league_logo(league_name)
                if league_logo.exists():
                    out["LEAGUE_LOGO"] = InlineImage(doc, str(league_logo), width=Mm(26))
    
    # Sponsor logo
    sponsor_path = out.get("SPONSOR_LOGO_PATH")
    if sponsor_path and pl.Path(sponsor_path).exists():
        out["SPONSOR_LOGO"] = InlineImage(doc, sponsor_path, width=Mm(50))
    else:
        sl = find_logo_by_name("SPONSOR_LOGO")
        if sl.exists():
            out["SPONSOR_LOGO"] = InlineImage(doc, str(sl), width=Mm(50))
    
    # Featured matchup logos
    for side in ("HOME", "AWAY"):
        name_key = f"{side}_TEAM_NAME"
        if out.get(name_key):
            team_name = out[name_key]
            debug_log_logo(team_name, kind="team")
            logo_path = find_team_logo(team_name)
            out[f"{side}_LOGO"] = InlineImage(doc, str(logo_path), width=Mm(20))
    
    # Game logos (for GAMES list) - ENHANCED for Unicode team names
    for g in out.get("GAMES", []):
        hn = g.get("HOME_TEAM_NAME")
        an = g.get("AWAY_TEAM_NAME")
        if hn:
            debug_log_logo(hn, kind="team")
            logo_path = find_team_logo(hn)
            g["HOME_LOGO"] = InlineImage(doc, str(logo_path), width=Mm(18))
        if an:
            debug_log_logo(an, kind="team")
            logo_path = find_team_logo(an)
            g["AWAY_LOGO"] = InlineImage(doc, str(logo_path), width=Mm(18))
    
    return out

# ---------------------- Main Build Function ----------------------
def _mask(s: str) -> str:
    """Mask sensitive strings for logging"""
    return f"{len(s)} chars" if s else "MISSING"

def main():
    """Main build function - PRODUCTION READY"""
    args = parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s"
    )
    
    # Determine week
    if args.auto_week:
        week = compute_fantasy_week(args.week_offset)
    else:
        week = args.week
    
    print("=== Build Configuration ===")
    print(f"Environment: {os.getenv('GITHUB_ENV', 'local') and 'actions' or 'local'}")
    print(f"Mode: single")
    print(f"Auto-week: {args.auto_week}")
    print(f"LLM Blurbs: {args.llm_blurbs}")
    print(f"Blurb Style: {args.blurb_style}")
    print(f"Year: {args.year}")
    print(f"Week: {week}")
    print(f"Output: ./{args.output_dir}/")
    print()
    
    # Preflight checks
    s2 = os.getenv("ESPN_S2", "")
    swid = os.getenv("SWID", "")
    print(f"[preflight] ESPN_S2: {_mask(s2)}, SWID: {_mask(swid)}")
    
    # Validate template
    template_path = pl.Path(args.template)
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {args.template}")
    
    # Prepare output
    out_dir = pl.Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    docx_path = out_dir / f"gazette_week_{week}.docx"
    
    if args.dry_run:
        print(f"[dry-run] Would build {docx_path}")
        sys.exit(0)
    
    # Validate logo mappings
    missing = validate_logo_map()
    if missing:
        print(f"[logo] Warning: {missing} mapped logo(s) are missing on disk.")
    
    # 1) Build context from our comprehensive data fetcher
    print("[build] Building context with comprehensive ESPN data...")
    ctx: Dict[str, Any] = assemble_context(
        league_id=args.league_id,
        year=args.year,
        week=week,
        llm_blurbs=args.llm_blurbs,
        blurb_style=args.blurb_style
    )
    
    # 2) Render DOCX with enhanced logo handling
    print("[build] Rendering DOCX template with enhanced logo support...")
    doc = DocxTemplate(str(template_path))
    ctx = attach_logos(doc, ctx)  # Enhanced logo injection with Unicode support
    doc.render(ctx)
    doc.save(str(docx_path))
    print(f"Output DOCX: {docx_path}")
    
    # 3) Add footer gradient if available
    if FOOTER_GRADIENT.exists():
        print("[build] Adding footer gradient...")
        add_footer_gradient(docx_path, FOOTER_GRADIENT, bar_height_mm=12.0)
    else:
        print(f"[footer] Gradient image not found at {FOOTER_GRADIENT}, skipping.")
    
    # 4) Convert to PDF and PDF/A
    print("[build] Converting to PDF...")
    pdf_path = docx_to_pdf(docx_path)
    print(f"PDF: {pdf_path}")
    
    print("[build] Converting to PDF/A...")
    pdfa_tmp = pdf_path.with_suffix(".pdfa.pdf")
    pdfa_path = pdf_to_pdfa(pdf_path, pdfa_tmp)
    print(f"PDF/A: {pdfa_path}")
    
    # 5) Optional PDF locking
    print("[build] Applying PDF security...")
    locked = pdf_path.with_suffix(".locked.pdf")
    final_pdf = lock_pdf_resilient(pdfa_path, locked)
    
    # Replace original PDF with locked PDF/A version
    try:
        pdf_path.unlink(missing_ok=True)
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