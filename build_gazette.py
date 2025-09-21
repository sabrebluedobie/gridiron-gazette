#!/usr/bin/env python3
# build_gazette.py — Gridiron Gazette production builder
# - DOCX render (docxtpl)
# - Stable diagonal gradient footer (table + inline image)
# - DOCX -> PDF (LibreOffice)
# - PDF -> PDF/A-2b (Ghostscript)
# - Optional lock (resilient if pikepdf missing)
# - JSON-driven logos for teams + league logo

import argparse, sys, os, subprocess, shlex, logging, datetime as dt, time
import pathlib as pl
from typing import Dict, Any

from docxtpl import DocxTemplate, InlineImage
from docx import Document
from docx.shared import Mm

from assets_fix import (
    find_team_logo, find_league_logo, debug_log_logo, validate_logo_map
)

# ---------------------- Configuration ----------------------
DEFAULT_TEMPLATE = "recap_template.docx"
DEFAULT_OUTDIR   = "recaps"
FOOTER_GRADIENT  = pl.Path("./logos/footer_gradient_diagonal.png")  # place the PNG here

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
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()

def compute_auto_week(offset: int = 0) -> int:
    today = dt.date.today()
    wk = int(today.strftime("%U"))
    return max(1, wk + offset)

# ---------------------- Footer helper ----------------------
def add_footer_gradient(docx_path: pl.Path, gradient_png: pl.Path, bar_height_mm: float = 12.0) -> None:
    doc = Document(str(docx_path))

    for section in doc.sections:
        # Keep footer from nudging
        section.bottom_margin = Mm(15)       # ~0.59"
        section.footer_distance = Mm(8)      # ~0.31"
        section.different_first_page_header_footer = False

        footer = section.footer
        # Wipe existing paragraphs/shapes in footer
        for p in list(footer.paragraphs):
            p._element.getparent().remove(p._element)

        # Compute content width (page − margins); pass width explicitly (python-docx variants need it)
        content_width = section.page_width - section.left_margin - section.right_margin
        tbl = footer.add_table(rows=2, cols=1, width=content_width)
        tbl.autofit = False
        # Fill width
        tbl.columns[0].width = content_width
        for row in tbl.rows:
            row.cells[0].width = content_width

        # Row 1: gradient strip
        run = tbl.rows[0].cells[0].paragraphs[0].add_run()
        try:
            pic = run.add_picture(str(gradient_png))
            pic.height = Mm(bar_height_mm)   # width will match cell
        except Exception as e:
            print(f"[footer] Could not add gradient image: {e}")

        # Row 2: hold footer text (template-managed or left blank)
        tbl.rows[1].cells[0].paragraphs[0].add_run("")
    doc.save(str(docx_path))

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

# ---------------------- Context assembly -------------------
def assemble_context(league_id: str, year: int, week: int, llm_blurbs: bool) -> Dict[str, Any]:
    """
    Wire this to your real data/templating code.
    If you already have a function for context, call it here instead of this stub.
    """
    # Replace this stub with your actual context builder if available.
    # If you have a function for context, call it here.
    return {
        "LEAGUE_NAME": "Browns SEA/KC",
        "WEEK_NUM": week,
        "HOME_TEAM_NAME": "Nana's Hawks",
        "AWAY_TEAM_NAME": "Phoenix Blues",
        "GAMES": [],
        "AWARDS": [],
        "GENERATED_AT": dt.datetime.now().isoformat(timespec="seconds"),
    }

def attach_logos(doc: DocxTemplate, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    JSON-first logo injection:
      - League logo from LEAGUE_LOGO_NAME or LEAGUE_NAME
      - Home/Away team logos from *_TEAM_NAME
      - Per-game team logos under GAMES list
    """
    out = dict(ctx)

    # League logo — prefer explicit name, else use league display name
    league_name = out.get("LEAGUE_LOGO_NAME") or out.get("LEAGUE_NAME")
    if league_name:
        debug_log_logo(league_name, kind="league")
        league_logo = find_league_logo(league_name)
        out["LEAGUE_LOGO"] = InlineImage(doc, str(league_logo), width=Mm(26))

    # Single-match (top block) team logos if present
    for side in ("HOME", "AWAY"):
        name_key = f"{side}_TEAM_NAME"
        if out.get(name_key):
            team_name = out[name_key]
            debug_log_logo(team_name, kind="team")
            logo_path = find_team_logo(team_name)
            out[f"{side}_LOGO"] = InlineImage(doc, str(logo_path), width=Mm(20))

    # Per-game entries
    games = out.get("GAMES", [])
    for g in games:
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
def main():
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")
    week = args.week if not args.auto_week else compute_auto_week(args.week_offset)

    print("=== Building Gridiron Gazette ===")
    print(f"Template: {args.template}")
    print(f"Output dir: {args.output_dir}")
    print(f"League ID: {args.league_id}")
    print(f"Year: {args.year}")
    print(f"Week: {week}")
    print(f"LLM Blurbs: {args.llm_blurbs}\n")

    try:
        template_path = pl.Path(args.template)
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {args.template}")

        out_dir = pl.Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        docx_path = out_dir / f"gazette_week_{week}.docx"

        if args.dry_run:
            print(f"[dry-run] Would build {docx_path}")
            sys.exit(0)

        # Preflight: JSON map sanity
        missing = validate_logo_map()
        if missing:
            print(f"[logo] Warning: {missing} mapped logo(s) are missing on disk.")

        # 1) Build context from data
        ctx = assemble_context(args.league_id, args.year, week, args.llm_blurbs)

        # 2) Render DOCX
        doc = DocxTemplate(str(template_path))
        ctx = attach_logos(doc, ctx)      # inject InlineImage fields
        doc.render(ctx)
        doc.save(str(docx_path))
        print(f"Output DOCX: {docx_path}")

        # 3) Stable footer gradient
        add_footer_gradient(docx_path, FOOTER_GRADIENT, bar_height_mm=12.0)

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
            pdf_path.unlink(missing_ok=True)
        except TypeError:
            if pdf_path.exists():
                os.remove(str(pdf_path))
        final_pdf.rename(pdf_path)
        print(f"[build] Final PDF/A at: {pdf_path}")

        print("[build] SUCCESS")
        sys.exit(0)

    except subprocess.CalledProcessError as e:
        logging.exception("External tool failed: %s", e)
        sys.exit(2)
    except Exception as e:
        logging.exception("Error building gazette: %s", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
