#!/usr/bin/env python3
"""
Generate styled Weekly Gazette DOCX/PDF files for one or many leagues.
"""

from __future__ import annotations

import argparse, json, os, re, sys, subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# -------------------------------------------------------------------
# Env flags (data fetch behavior)
# -------------------------------------------------------------------
FORCE_LIVE  = os.getenv("FORCE_LIVE", "0").lower() in ("1","true","yes","on")
NO_CACHE    = os.getenv("NO_CACHE", "0").lower() in ("1","true","yes","on")
CACHE_TTL_S = int(os.getenv("CACHE_TTL_S", "0") or 0)
STATS_DEPTH = os.getenv("STATS_DEPTH", "summary")  # "summary" | "box"

# 3rd party
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

# Local modules
try:
    from gazette_data import build_context, fetch_week_from_espn
except Exception as e:
    print("Error:  Unable to import gazette_data. Run from repo root.", e, file=sys.stderr)
    raise

# -------------------------------------------------------------------
# PDF helpers (unchanged)
# -------------------------------------------------------------------
def to_pdf_with_soffice(docx_path: str) -> str:
    outdir = os.path.dirname(docx_path) or "."
    pdf_path = os.path.splitext(docx_path)[0] + ".pdf"
    cmd = ["soffice", "--headless", "--convert-to", "pdf", "--outdir", outdir, docx_path]
    try:
        subprocess.run(cmd, check=True)
    except Exception:
        cmd[0] = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
        subprocess.run(cmd, check=True)
    return pdf_path

def to_pdf_with_docx2pdf(docx_path: str) -> str:
    from docx2pdf import convert as _convert  # type: ignore
    pdf_path = os.path.splitext(docx_path)[0] + ".pdf"
    _convert(docx_path, pdf_path)
    return pdf_path

def to_pdf(docx_path: str, engine: str = "auto") -> str:
    if engine == "soffice":
        return to_pdf_with_soffice(docx_path)
    if engine == "docx2pdf":
        try: return to_pdf_with_docx2pdf(docx_path)
        except Exception: return to_pdf_with_soffice(docx_path)
    try: return to_pdf_with_docx2pdf(docx_path)
    except Exception: return to_pdf_with_soffice(docx_path)

# -------------------------------------------------------------------
# Logo + context helpers (unchanged from your file)
# -------------------------------------------------------------------
# ... [KEEP the find_logo_path, add_logo_images, add_branding_images,
# add_enumerated_matchups, add_template_synonyms, _safe_get_missing]
# -------------------------------------------------------------------

# -------------------------------------------------------------------
# LLM blurb JSON expander (unchanged)
# -------------------------------------------------------------------
# ... [KEEP maybe_expand_blurbs_json as-is]
# -------------------------------------------------------------------

def safe_title(s: str) -> str:
    s = re.sub(r"[^\w\s\-\(\)\._]", "_", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s

# -------------------------------------------------------------------
# Renderers (unchanged, except they already call maybe_expand_blurbs_json)
# -------------------------------------------------------------------
# ... [KEEP render_single_league, render_branding_test]
# -------------------------------------------------------------------

# -------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", default="leagues.json")
    ap.add_argument("--template", default="recap_template.docx")
    ap.add_argument("--out-dir", default="recaps")
    ap.add_argument("--pdf", action="store_true")
    ap.add_argument("--pdf-engine", default="auto", choices=["auto","soffice","docx2pdf"])
    ap.add_argument("--league", default=None)
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--week-label", default=None)
    ap.add_argument("--date", default=None)
    ap.add_argument("--slots", type=int, default=10)
    ap.add_argument("--logo-mm", type=int, default=25)
    ap.add_argument("--print-logo-map", action="store_true")
    ap.add_argument("--branding-test", action="store_true")
    ap.add_argument("--blurb-test", action="store_true",
        help="Quick LLM blurb test: sensible defaults, no PDF unless --pdf.")

    # LLM options
    ap.add_argument("--llm-blurbs", action="store_true")
    ap.add_argument("--blurb-words", type=int, default=150)
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--temperature", type=float, default=0.4)
    ap.add_argument("--blurb-style", default=None)

    return ap.parse_args()

# -------------------------------------------------------------------
# Blurb test presets
# -------------------------------------------------------------------
def _apply_blurb_test_presets(args):
    if not getattr(args, "blurb_test", False): return args
    if not args.week: args.week = 1
    if not args.slots: args.slots = 10
    if not args.llm_blurbs: args.llm_blurbs = True
    if not args.blurb_words: args.blurb_words = 1000
    if not args.model: args.model = "gpt-4o-mini"
    if not args.temperature: args.temperature = 0.4
    if hasattr(args, "blurb_style") and not args.blurb_style:
        args.blurb_style = "rtg"
    if not args.pdf: args.pdf = False
    print(f"[blurb-test] Using presets: week={args.week}, slots={args.slots}, "
          f"words={args.blurb_words}, model={args.model}, temp={args.temperature}, "
          f"style={args.blurb_style}, pdf={args.pdf}")
    return args

# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------
def main() -> None:
    args = parse_args()
    args = _apply_blurb_test_presets(args)

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
        print("[warn] No leagues matched filter; nothing to do.")
        sys.exit(0)

    for cfg in items:
        if args.branding_test:
            docx_path, pdf_path, _ = render_branding_test(cfg, args)
        else:
            docx_path, pdf_path, _ = render_single_league(cfg, args)

        print(f"[ok] Wrote DOCX: {Path(docx_path).resolve()}")
        if pdf_path: print(f"[ok] Wrote PDF: {Path(pdf_path).resolve()}")

if __name__ == "__main__":
    main()