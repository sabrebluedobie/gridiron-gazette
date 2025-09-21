#!/usr/bin/env python3
"""
build_gazette.py — Integrated DOCX builder for Gridiron Gazette

Fixed to properly integrate:
- ESPN data fetching (gazette_data.py)
- LLM blurb generation (storymaker.py + OpenAI)
- Logo resolution (unified via logo_resolver.py or mascots_util.py)
- Template rendering (docxtpl)
- Optional PDF export
"""

import argparse
import sys
import os
import subprocess
import shlex
import logging
import datetime as dt
import time
import json
import pathlib as pl
from typing import Dict, Any, Optional

# Third-party
from docxtpl import DocxTemplate, InlineImage
from docx import Document
from docx.shared import Mm

# Local imports
from gazette_data import fetch_week_from_espn, build_context
from gazette_helpers import add_enumerated_matchups, add_template_synonyms

# Try new unified resolver first, fallback to existing
try:
    from logo_resolver import team_logo, league_logo, sponsor_logo
except ImportError:
    from mascots_util import logo_for as team_logo
    def league_logo(name): return None
    def sponsor_logo(name): return None

# Import OpenAI for LLM blurbs
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


# ======================================================================
# Configuration defaults
# ======================================================================
DEFAULT_TEMPLATE = "recap_template.docx"
DEFAULT_OUTDIR = "recaps"
LOGO_ROOT = pl.Path("./logos/team_logos")
FOOTER_GRADIENT = pl.Path("./logos/footer_gradient_diagonal.png")
PREFERRED_IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


# ======================================================================
# Argparse
# ======================================================================
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build Gridiron Gazette DOCX")
    p.add_argument("--league-id", required=True, help="ESPN League ID")
    p.add_argument("--year", type=int, required=True, help="Season year")
    
    # Week selection
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--week", type=int, help="Specific week number")
    g.add_argument("--auto-week", action="store_true", help="Auto-detect current week")
    
    p.add_argument("--week-offset", type=int, default=0, help="Offset for auto-week")
    p.add_argument("--template", default=DEFAULT_TEMPLATE, help="Template DOCX path")
    p.add_argument("--output-dir", default=DEFAULT_OUTDIR, help="Output directory")
    
    # LLM options
    p.add_argument("--llm-blurbs", action="store_true", help="Generate AI blurbs")
    p.add_argument("--blurb-words", type=int, default=300, help="Target words per blurb")
    p.add_argument("--blurb-style", default="sabre", help="Blurb style (sabre/mascot/default)")
    p.add_argument("--model", default="gpt-4o-mini", help="OpenAI model")
    p.add_argument("--temperature", type=float, default=0.7, help="LLM temperature")
    
    # Layout
    p.add_argument("--slots", type=int, default=10, help="Max matchup slots in template")
    p.add_argument("--logo-mm", type=float, default=25.0, help="Logo width in mm")
    
    # Options
    p.add_argument("--dry-run", action="store_true", help="Don't actually build")
    p.add_argument("--verbose", action="store_true", help="Verbose output")
    p.add_argument("--no-pdf", action="store_true", help="Skip PDF generation")
    
    return p.parse_args()


def compute_auto_week(offset: int = 0) -> int:
    """Simple auto-week using ISO week number"""
    today = dt.date.today()
    wk = int(today.strftime("%U"))
    return max(1, wk + offset)


# ======================================================================
# LLM Integration
# ======================================================================
def generate_llm_blurb(
    game: Dict[str, Any],
    style: str = "sabre",
    model: str = "gpt-4o-mini",
    temperature: float = 0.7,
    max_words: int = 300
) -> str:
    """Generate LLM blurb for a single game"""
    
    if not OPENAI_AVAILABLE:
        return f"{game['home']} vs {game['away']}"
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[LLM] No OPENAI_API_KEY, skipping blurb generation")
        return f"{game['home']} vs {game['away']}"
    
    # Load Sabre prompt from storymaker
    try:
        from storymaker import SABRE_STORY_PROMPT
        system_prompt = SABRE_STORY_PROMPT if style == "sabre" else (
            f"You are a witty fantasy football writer. Write {max_words}-word game recaps."
        )
    except ImportError:
        system_prompt = f"Write a {max_words}-word fantasy football recap."
    
    # Build user prompt with game details
    user_prompt = f"""
Game Details:
- Home: {game['home']} (Score: {game.get('hs', 'TBD')})
- Away: {game['away']} (Score: {game.get('as', 'TBD')})
- Top Home: {game.get('top_home', 'N/A')}
- Top Away: {game.get('top_away', 'N/A')}
- Bust: {game.get('bust', 'N/A')}
- Key Play: {game.get('keyplay', 'N/A')}
- Defense: {game.get('def', 'N/A')}

Write a {max_words}-word recap.
"""
    
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature,
            max_tokens=max_words * 2
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[LLM] Error: {e}")
        return f"{game['home']} vs {game['away']}"


def enhance_games_with_llm(games, enable_llm, **kwargs):
    """Add LLM blurbs to games that don't have them"""
    if not enable_llm:
        return games
    
    for i, game in enumerate(games, 1):
        if not game.get('blurb'):
            print(f"[LLM] Generating blurb {i}/{len(games)}")
            game['blurb'] = generate_llm_blurb(game, **kwargs)
    
    return games


# ======================================================================
# Logo Integration
# ======================================================================
def attach_logo_images(doc: DocxTemplate, ctx: Dict[str, Any], logo_mm: float, max_slots: int) -> Dict[str, Any]:
    """Convert logo paths/team names to InlineImage objects"""
    
    for i in range(1, max_slots + 1):
        # Home team logo
        home = ctx.get(f"MATCHUP{i}_HOME", "")
        if home:
            logo_path = team_logo(home)
            if logo_path and pl.Path(logo_path).exists():
                ctx[f"MATCHUP{i}_HOME_LOGO"] = InlineImage(
                    doc, str(logo_path), width=Mm(logo_mm)
                )
        
        # Away team logo
        away = ctx.get(f"MATCHUP{i}_AWAY", "")
        if away:
            logo_path = team_logo(away)
            if logo_path and pl.Path(logo_path).exists():
                ctx[f"MATCHUP{i}_AWAY_LOGO"] = InlineImage(
                    doc, str(logo_path), width=Mm(logo_mm)
                )
    
    # League logo (if configured)
    league_name = ctx.get('title', '')
    if league_name:
        logo_path = league_logo(league_name)
        if logo_path and pl.Path(logo_path).exists():
            ctx['LEAGUE_LOGO'] = InlineImage(doc, str(logo_path), width=Mm(logo_mm))
    
    # Sponsor logo (if configured)
    sponsor = ctx.get('sponsor', {})
    if sponsor and sponsor.get('name'):
        logo_path = sponsor_logo(sponsor['name'])
        if logo_path and pl.Path(logo_path).exists():
            ctx['SPONSOR_LOGO'] = InlineImage(doc, str(logo_path), width=Mm(logo_mm))
    
    return ctx


# ======================================================================
# PDF Export (optional)
# ======================================================================
def docx_to_pdf(docx_path: pl.Path, out_dir: pl.Path = None) -> pl.Path:
    """Convert DOCX to PDF using LibreOffice"""
    docx = docx_path.resolve()
    outd = (out_dir or docx.parent).resolve()
    outd.mkdir(parents=True, exist_ok=True)
    
    cmd = f'soffice --headless --nologo --nolockcheck --convert-to pdf --outdir {shlex.quote(str(outd))} {shlex.quote(str(docx))}'
    subprocess.run(cmd, shell=True, check=True)
    
    pdf_path = outd / (docx.stem + ".pdf")
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not created: {pdf_path}")
    return pdf_path


# ======================================================================
# Main Build Function
# ======================================================================
def main():
    args = parse_args()
    
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s"
    )
    
    # Determine week
    week = args.week if args.week is not None else compute_auto_week(args.week_offset)
    
    print("=== Building Gridiron Gazette ===")
    print(f"League ID: {args.league_id}")
    print(f"Year: {args.year}")
    print(f"Week: {week}")
    print(f"LLM Blurbs: {args.llm_blurbs}")
    print(f"Template: {args.template}\n")
    
    if args.dry_run:
        print("[DRY RUN] Would build gazette with above settings")
        sys.exit(0)
    
    try:
        # 1) Fetch ESPN data
        print("[1/6] Fetching ESPN data...")
        
        # Get credentials from env (for CI/CD) or load from leagues.json
        espn_s2 = os.getenv("ESPN_S2", "")
        swid = os.getenv("SWID", "")
        
        if not espn_s2 or not swid:
            # Try loading from leagues.json
            leagues_file = pl.Path("leagues.json")
            if leagues_file.exists():
                leagues = json.loads(leagues_file.read_text())
                if isinstance(leagues, list) and leagues:
                    cfg = leagues[0]
                    espn_s2 = cfg.get("espn_s2", "")
                    swid = cfg.get("swid", "")
        
        games = fetch_week_from_espn(
            league_id=int(args.league_id),
            year=args.year,
            espn_s2=espn_s2,
            swid=swid,
            week=week
        )
        
        if not games:
            raise ValueError("No games found from ESPN API")
        
        print(f"   Found {len(games)} games")
        
        # 2) Enhance with LLM blurbs
        if args.llm_blurbs:
            print("[2/6] Generating LLM blurbs...")
            games = enhance_games_with_llm(
                games,
                enable_llm=True,
                style=args.blurb_style,
                model=args.model,
                temperature=args.temperature,
                max_words=args.blurb_words
            )
        else:
            print("[2/6] Skipping LLM blurbs")
        
        # 3) Build context
        print("[3/6] Building context...")
        
        # Load league config for title/sponsor
        cfg = {"league_id": args.league_id, "year": args.year, "week": week}
        leagues_file = pl.Path("leagues.json")
        if leagues_file.exists():
            leagues = json.loads(leagues_file.read_text())
            if isinstance(leagues, list):
                for league in leagues:
                    if str(league.get("league_id")) == str(args.league_id):
                        cfg = league
                        break
        
        ctx = build_context(cfg, games)
        ctx['week_num'] = week
        
        # Expand matchups for template
        add_enumerated_matchups(ctx, args.slots)
        add_template_synonyms(ctx, args.slots)
        
        # 4) Load template and attach images
        print("[4/6] Rendering template...")
        template_path = pl.Path(args.template)
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {args.template}")
        
        doc = DocxTemplate(str(template_path))
        ctx = attach_logo_images(doc, ctx, args.logo_mm, args.slots)
        
        # Render
        doc.render(ctx)
        
        # 5) Save DOCX
        print("[5/6] Saving DOCX...")
        out_dir = pl.Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        
        league_slug = cfg.get('short_name', cfg.get('name', 'league')).replace(' ', '_')
        docx_path = out_dir / f"{league_slug}_week_{week}.docx"
        
        doc.save(str(docx_path))
        print(f"   Saved: {docx_path}")
        
        # 6) Optional PDF
        if not args.no_pdf:
            print("[6/6] Converting to PDF...")
            try:
                pdf_path = docx_to_pdf(docx_path)
                print(f"   PDF: {pdf_path}")
            except Exception as e:
                print(f"   PDF conversion failed: {e}")
        else:
            print("[6/6] Skipping PDF")
        
        print("\n[SUCCESS] Gazette built successfully!")
        sys.exit(0)
        
    except Exception as e:
        logging.exception("Error building gazette: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()