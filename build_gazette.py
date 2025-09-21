#!/usr/bin/env python3
# build_gazette.py — Gridiron Gazette: DOCX -> PDF/A with stable footer + reliable logos
# Safe for CI/beta: robust args, pathlib only, graceful fallbacks, professional outputs.

import argparse, sys, os, subprocess, shlex, logging, datetime as dt, time, json
import pathlib as pl
from typing import Dict, Any

# ---------- Third-party deps you likely already have ----------
# docxtpl for templating; python-docx for post-processing footer
from docxtpl import DocxTemplate, InlineImage
from docx import Document
from docx.shared import Mm

# Try to import pikepdf lazily inside lock step (we handle fallback)
# from scripts.lock_pdf import lock_pdf   # optional external; we also embed a safe fallback below


# ======================================================================
# Configuration defaults (edit as needed)
# ======================================================================
DEFAULT_TEMPLATE = "recap_template.docx"
DEFAULT_OUTDIR   = "recaps"
LOGO_ROOT        = pl.Path("./logos/team_logos")
FOOTER_GRADIENT  = pl.Path("./logos/footer_gradient_diagonal.png")  # place file here
PREFERRED_IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
ALL_IMAGE_EXTS       = PREFERRED_IMAGE_EXTS | {".webp", ".gif", ".bmp", ".tif", ".tiff"}

# If you want a hard placeholder logo, put it here (optional):
PLACEHOLDER_LOGO = LOGO_ROOT / "placeholder.png"

# One-off overrides (exact file name) — your Nana’s Hawks case:
NAME_OVERRIDES = {
    "nana's hawks": "Nanas_Hawks.png",
}


# ======================================================================
# Argparse / Orchestration
# ======================================================================
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
    # Simple and safe: use ISO week-of-year as placeholder. Customize later if needed.
    today = dt.date.today()
    wk = int(today.strftime("%U"))
    return max(1, wk + offset)


# ======================================================================
# Asset helpers — stable footer gradient + bulletproof logos
# ======================================================================
def add_footer_gradient(docx_path: pl.Path, gradient_png: pl.Path, bar_height_mm: float = 12.0) -> None:
    """Replace any legacy footer content with a 2-row table; row1 is a gradient strip (inline image)."""
    doc = Document(str(docx_path))
    for section in doc.sections:
        section.bottom_margin = Mm(15)   # ~0.59"
        section.footer_distance = Mm(8)  # ~0.31"
        section.different_first_page_header_footer = False

        footer = section.footer
        # Clear old paragraphs/shapes
        for p in list(footer.paragraphs):
            p._element.getparent().remove(p._element)

        # New footer table
        tbl = footer.add_table(rows=2, cols=1)
        tbl.autofit = True

        # Row 1: gradient strip as inline picture
        run = tbl.rows[0].cells[0].paragraphs[0].add_run()
        if gradient_png.exists():
            pic = run.add_picture(str(gradient_png))
            pic.height = Mm(bar_height_mm)
        else:
            # If not present, just add a blank run so layout stays stable
            tbl.rows[0].cells[0].paragraphs[0].add_run("")

        # Row 2: reserved for footer text (template may add this, we keep a blank line)
        tbl.rows[1].cells[0].paragraphs[0].add_run("")
    doc.save(str(docx_path))


def _sanitize_name(name: str) -> str:
    import re
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def _ensure_png(src: pl.Path) -> pl.Path:
    # Convert WEBP/GIF/etc to PNG so python-docx is happy
    if src.suffix.lower() in PREFERRED_IMAGE_EXTS:
        return src
    try:
        from PIL import Image
        out = src.with_suffix(".png")
        im = Image.open(str(src)).convert("RGBA")
        out.parent.mkdir(parents=True, exist_ok=True)
        im.save(str(out), format="PNG")
        return out
    except Exception:
        return src


def find_team_logo(team_name: str) -> pl.Path:
    """Robust resolver: overrides -> normalized guesses -> any ext (convert) -> placeholder"""
    lowered = team_name.lower()
    # explicit override?
    if lowered in NAME_OVERRIDES:
        fp = LOGO_ROOT / NAME_OVERRIDES[lowered]
        if fp.exists():
            return fp

    key = _sanitize_name(team_name)  # "Nana's Hawks" -> "nana_s_hawks"
    variants = {
        key,
        key.replace("_s_", "s_"),      # "nanas_hawks"
        key.replace("_s_", "_"),
        key.replace("__", "_"),
        key.rstrip("_"),
    }

    # Preferred first
    for base in variants:
        for ext in PREFERRED_IMAGE_EXTS:
            p = LOGO_ROOT / f"{base}{ext}"
            if p.exists():
                return p

    # Then any ext, convert to PNG if needed
    for base in variants:
        for ext in ALL_IMAGE_EXTS:
            p = LOGO_ROOT / f"{base}{ext}"
            if p.exists():
                return _ensure_png(p)

    # Fallback
    return PLACEHOLDER_LOGO if PLACEHOLDER_LOGO.exists() else LOGO_ROOT / "MISSING.png"


def debug_log_logo(team_name: str) -> None:
    p = find_team_logo(team_name)
    note = ""
    if not p.exists():
        note = " (NOT FOUND)"
    elif p.suffix.lower() not in PREFERRED_IMAGE_EXTS:
        note = f" (non-preferred: {p.suffix})"
    print(f"[logo] {team_name} -> {p}{note}")


def attach_images(doc: DocxTemplate, ctx: Dict[str, Any], logo_mm: float = 20.0) -> Dict[str, Any]:
    """
    Convert *_LOGO_PATH or *_TEAM_NAME into InlineImage objects the template expects:
      - HOME_TEAM_NAME -> HOME_LOGO
      - AWAY_TEAM_NAME -> AWAY_LOGO
      - Also honors *_LOGO_PATH if you already set explicit paths.
    """
    out = dict(ctx)

    # 1) Honor explicit *_LOGO_PATH if present
    for k, v in list(ctx.items()):
        if k.endswith("_LOGO_PATH") and v:
            p = pl.Path(str(v))
            slot = k.replace("_PATH", "")  # *_LOGO
            if p.exists() and p.suffix.lower() in (PREFERRED_IMAGE_EXTS | {".webp", ".gif", ".bmp", ".tif", ".tiff"}):
                try:
                    out[slot] = InlineImage(doc, str(_ensure_png(p)), width=Mm(logo_mm))
                    print(f"[logo] Loaded explicit {slot}: {p}")
                except Exception as e:
                    print(f"[logo] Failed explicit {slot} {p}: {e}")

    # 2) Resolve via *_TEAM_NAME if slot not filled
    for k, v in list(ctx.items()):
        if k.endswith("_TEAM_NAME") and v:
            base = k[:-10]              # strip "_TEAM_NAME"
            slot = f"{base}_LOGO"       # e.g., HOME_LOGO
            if slot in out and isinstance(out[slot], InlineImage):
                continue
            team_name = str(v)
            try:
                debug_log_logo(team_name)
                lp = find_team_logo(team_name)
                out[slot] = InlineImage(doc, str(lp), width=Mm(logo_mm))
                print(f"[logo] Resolved {team_name} -> {lp.name} for {slot}")
            except Exception as e:
                print(f"[logo] Resolution error for {team_name}: {e}")

    return out


# ======================================================================
# DOCX -> PDF -> PDF/A (+ optional lock)
# ======================================================================
def docx_to_pdf(docx_path: pl.Path, out_dir: pl.Path | None = None) -> pl.Path:
    docx = docx_path.resolve()
    outd = (out_dir or docx.parent).resolve()
    outd.mkdir(parents=True, exist_ok=True)
    cmd = f'soffice --headless --nologo --nolockcheck --convert-to pdf --outdir {shlex.quote(str(outd))} {shlex.quote(str(docx))}'
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
    """Try to lock with pikepdf; if unavailable or fails, copy unlocked."""
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


# ======================================================================
# Build context (hook your existing logic here)
# ======================================================================
def assemble_context(league_id: str, year: int, week: int, llm_blurbs: bool) -> Dict[str, Any]:
    """
    This is the only place you may need to adapt to your repo.
    If you already have a function that returns the template context, call it here.
    """
    # Use fallback context logic since gazette_runner cannot be imported.
    # Minimal stub so script structure is clear.
    # Replace with your real context keys (team names, stats, awards, etc.)
    return {
        "LEAGUE_NAME": "Browns SEA/KC",
        "WEEK_NUM": week,
        # Example keys your template likely expects per game:
        "HOME_TEAM_NAME": "Nana's Hawks",
        "AWAY_TEAM_NAME": "Phoenix Blues",
        # Any *_LOGO_PATH can still be provided; resolver will honor or fallback by TEAM_NAME
        # "HOME_LOGO_PATH": "./logos/team_logos/Nanas_Hawks.png",
        # "AWAY_LOGO_PATH": "./logos/team_logos/Phoenix_Blues.png",
        "GAMES": [],          # your list of games/recaps
        "AWARDS": [],         # weekly awards
        "GENERATED_AT": dt.datetime.now().isoformat(timespec="seconds"),
    }



# ======================================================================
# Main
# ======================================================================
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

        # 1) Build context (hook into your existing logic)
        ctx = assemble_context(args.league_id, args.year, week, args.llm_blurbs)

        # 2) Render DOCX with docxtpl
        doc = DocxTemplate(str(template_path))
        ctx = attach_images(doc, ctx, logo_mm=20.0)  # converts logos to InlineImage safely
        doc.render(ctx)
        doc.save(str(docx_path))
        print(f"Output DOCX: {docx_path}")

        # 3) Add stable footer gradient (inline image in footer table)
        add_footer_gradient(docx_path, FOOTER_GRADIENT, bar_height_mm=12.0)

        # 4) DOCX -> PDF
        pdf_path = docx_to_pdf(docx_path)
        print(f"PDF: {pdf_path}")

        # 5) PDF -> PDF/A-2b (write to tmp, then replace)
        pdfa_tmp = pdf_path.with_suffix(".pdfa.pdf")
        pdfa_path = pdf_to_pdfa(pdf_path, pdfa_tmp)
        print(f"PDF/A: {pdfa_path}")

        # 6) Optional lock (resilient)
        locked_out = pdf_path.with_suffix(".locked.pdf")
        final_pdf = lock_pdf_resilient(pdfa_path, locked_out)
        # Replace the basic PDF with final locked/unlocked PDF/A under the standard name
        try:
            pdf_path.unlink(missing_ok=True)
        except TypeError:
            # Python <3.8 compatibility if ever needed
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
