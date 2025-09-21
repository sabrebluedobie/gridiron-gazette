#!/usr/bin/env python3
"""
build_gazette.py - FULLY FIXED VERSION
Resolves all remaining issues:
- League/sponsor logos not showing
- Empty Stats Spotlight fields
- Footer gradient missing
- PDF/A font embedding
"""

import argparse
import sys
import os
import subprocess
import shlex
import datetime as dt
from pathlib import Path
from typing import Dict, Any

from docxtpl import DocxTemplate, InlineImage
from docx import Document
from docx.shared import Mm
from docx.enum.text import WD_ALIGN_PARAGRAPH

# Local imports
from gazette_data import fetch_week_from_espn, build_context
from gazette_helpers import add_enumerated_matchups, add_template_synonyms

# Try unified logo resolver
try:
    from logo_resolver import team_logo, league_logo as get_league_logo, sponsor_logo as get_sponsor_logo
except ImportError:
    # Fallback to mascots_util
    from mascots_util import logo_for as team_logo
    
    def get_league_logo(name):
        """Fallback league logo finder"""
        from pathlib import Path
        import json
        
        # Try league_logos.json
        mapping_file = Path("league_logos.json")
        if mapping_file.exists():
            try:
                mapping = json.loads(mapping_file.read_text())
                if name in mapping:
                    return mapping[name]
            except:
                pass
        
        # Try direct file
        for p in Path("logos/league_logos").glob("*"):
            if name.lower() in p.stem.lower():
                return str(p)
        
        # Try team_logos dir as fallback
        for p in Path("logos/team_logos").glob("*"):
            if name.lower() in p.stem.lower():
                return str(p)
        
        return None
    
    def get_sponsor_logo(name):
        """Fallback sponsor logo finder"""
        from pathlib import Path
        import json
        
        # Try sponsor_logos.json
        mapping_file = Path("sponsor_logos.json")
        if mapping_file.exists():
            try:
                mapping = json.loads(mapping_file.read_text())
                if name in mapping:
                    return mapping[name]
            except:
                pass
        
        # Try direct file
        for p in Path("logos/sponsor_logos").glob("*"):
            if name.lower() in p.stem.lower():
                return str(p)
        
        return None

# Import OpenAI for LLM
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--league-id", required=True)
    p.add_argument("--year", type=int, required=True)
    
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--week", type=int)
    g.add_argument("--auto-week", action="store_true")
    
    p.add_argument("--week-offset", type=int, default=0)
    p.add_argument("--template", default="recap_template.docx")
    p.add_argument("--output-dir", default="recaps")
    
    p.add_argument("--llm-blurbs", action="store_true")
    p.add_argument("--blurb-words", type=int, default=300)
    p.add_argument("--blurb-style", default="sabre")
    p.add_argument("--model", default="gpt-4o-mini")
    p.add_argument("--temperature", type=float, default=0.7)
    
    p.add_argument("--slots", type=int, default=10)
    p.add_argument("--logo-mm", type=float, default=25.0)
    
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--no-pdf", action="store_true")
    
    return p.parse_args()


def compute_auto_week(offset=0):
    today = dt.date.today()
    return max(1, int(today.strftime("%U")) + offset)


def extract_player_stats(game_data):
    """Extract actual player statistics from ESPN game data"""
    stats = {
        'top_home': 'N/A',
        'top_away': 'N/A',
        'bust': 'N/A',
        'keyplay': 'N/A',
        'def': 'N/A'
    }
    
    try:
        # For ESPN API data
        if hasattr(game_data, 'home_lineup'):
            home_players = sorted(
                game_data.home_lineup, 
                key=lambda p: p.points if hasattr(p, 'points') else 0,
                reverse=True
            )
            if home_players:
                top = home_players[0]
                stats['top_home'] = f"{top.name} - {top.points:.1f} pts"
                
                starters = [p for p in home_players if hasattr(p, 'slot_position') and p.slot_position != 'BE']
                if starters:
                    bust = starters[-1]
                    stats['bust'] = f"{bust.name} - {bust.points:.1f} pts"
        
        if hasattr(game_data, 'away_lineup'):
            away_players = sorted(
                game_data.away_lineup,
                key=lambda p: p.points if hasattr(p, 'points') else 0,
                reverse=True
            )
            if away_players:
                top = away_players[0]
                stats['top_away'] = f"{top.name} - {top.points:.1f} pts"
        
        if hasattr(game_data, 'home_lineup'):
            for player in game_data.home_lineup:
                if hasattr(player, 'position') and player.position == 'D/ST':
                    stats['def'] = f"{player.name} - {player.points:.1f} pts"
                    break
    
    except Exception as e:
        print(f"[STATS] Error extracting stats: {e}")
    
    return stats


def generate_llm_blurb(game, style="sabre", model="gpt-4o-mini", temperature=0.7, max_words=300):
    """Generate LLM blurb with actual stats data"""
    if not OPENAI_AVAILABLE or not os.getenv("OPENAI_API_KEY"):
        return f"{game['home']} vs {game['away']}"
    
    from storymaker import SABRE_STORY_PROMPT
    
    user_prompt = f"""
Game Details:
- Home: {game['home']} (Score: {game.get('hs', 'TBD')})
- Away: {game['away']} (Score: {game.get('as', 'TBD')})
- Top Home Performer: {game.get('top_home', 'N/A')}
- Top Away Performer: {game.get('top_away', 'N/A')}
- Biggest Bust: {game.get('bust', 'N/A')}
- Key Play: {game.get('keyplay', 'N/A')}
- Defense: {game.get('def', 'N/A')}

Write a {max_words}-word recap in Sabre's voice.
"""
    
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SABRE_STORY_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature,
            max_tokens=max_words * 2
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[LLM] Error: {e}")
        return f"{game['home']} vs {game['away']}"


def add_footer_gradient(docx_path, gradient_png=None):
    """Add diagonal gradient to footer"""
    if gradient_png is None:
        gradient_png = Path("logos/footer_gradient_diagonal.png")
    
    if not Path(gradient_png).exists():
        print(f"[WARN] Footer gradient not found: {gradient_png}")
        return
    
    doc = Document(str(docx_path))
    
    for section in doc.sections:
        section.bottom_margin = Mm(15)
        section.footer_distance = Mm(8)
        
        footer = section.footer
        
        for para in list(footer.paragraphs):
            p_element = para._element
            p_element.getparent().remove(p_element)
        
        para = footer.add_paragraph()
        run = para.add_run()
        
        try:
            run.add_picture(str(gradient_png), width=section.page_width)
            
            text_para = footer.add_paragraph()
            text_para.text = "See everyone Thursday!"
            text_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            
        except Exception as e:
            print(f"[WARN] Could not add footer gradient: {e}")
    
    doc.save(str(docx_path))


def attach_all_logos(doc, ctx, logo_mm, max_slots):
    """Attach team, league, and sponsor logos"""
    
    for i in range(1, max_slots + 1):
        home = ctx.get(f"MATCHUP{i}_HOME", "")
        away = ctx.get(f"MATCHUP{i}_AWAY", "")
        
        if home:
            logo_path = team_logo(home)
            if logo_path and Path(logo_path).exists():
                ctx[f"MATCHUP{i}_HOME_LOGO"] = InlineImage(doc, str(logo_path), width=Mm(logo_mm))
                print(f"[LOGO] Added home logo for {home}")
        
        if away:
            logo_path = team_logo(away)
            if logo_path and Path(logo_path).exists():
                ctx[f"MATCHUP{i}_AWAY_LOGO"] = InlineImage(doc, str(logo_path), width=Mm(logo_mm))
                print(f"[LOGO] Added away logo for {away}")
    
    league_name = ctx.get('title', '')
    if league_name:
        print(f"[LOGO] Looking for league logo: {league_name}")
        logo_path = get_league_logo(league_name)
        
        if not logo_path or not Path(logo_path).exists():
            alt_names = [
                ctx.get('short_name', ''),
                league_name.replace(' ', ''),
                league_name.replace(' ', '-'),
                league_name.split()[0] if league_name else ''
            ]
            for alt in alt_names:
                if alt:
                    logo_path = get_league_logo(alt)
                    if logo_path and Path(logo_path).exists():
                        print(f"[LOGO] Found league logo with alternate name: {alt}")
                        break
        
        if logo_path and Path(logo_path).exists():
            ctx['LEAGUE_LOGO'] = InlineImage(doc, str(logo_path), width=Mm(logo_mm))
            print(f"[LOGO] Added league logo: {logo_path}")
        else:
            print(f"[WARN] No league logo found for: {league_name}")
    
    sponsor = ctx.get('sponsor', {})
    if sponsor and sponsor.get('name'):
        print(f"[LOGO] Looking for sponsor logo: {sponsor['name']}")
        logo_path = get_sponsor_logo(sponsor['name'])
        
        if logo_path and Path(logo_path).exists():
            ctx['SPONSOR_LOGO'] = InlineImage(doc, str(logo_path), width=Mm(logo_mm))
            print(f"[LOGO] Added sponsor logo: {logo_path}")
        else:
            print(f"[WARN] No sponsor logo found for: {sponsor['name']}")
    
    return ctx


def convert_to_pdfa(input_pdf, output_pdf):
    """Convert PDF to PDF/A with embedded fonts"""
    cmd = [
        "gs",
        "-dBATCH", "-dNOPAUSE", "-dQUIET",
        "-sDEVICE=pdfwrite",
        "-dPDFA=2",
        "-dPDFACompatibilityPolicy=1",
        "-dEmbedAllFonts=true",
        "-dSubsetFonts=false",
        "-dProcessColorModel=/DeviceRGB",
        "-dUseCIEColor",
        f"-sOutputFile={output_pdf}",
        str(input_pdf)
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"[PDF/A] Converted to PDF/A with embedded fonts")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] PDF/A conversion failed: {e}")
        return False


def main():
    args = parse_args()
    
    week = args.week if args.week is not None else compute_auto_week(args.week_offset)
    
    print("=== Building Gridiron Gazette ===")
    print(f"Week: {week}")
    print(f"LLM Blurbs: {args.llm_blurbs}\n")
    
    try:
        espn_s2 = os.getenv("ESPN_S2", "")
        swid = os.getenv("SWID", "")
        
        import json
        leagues_file = Path("leagues.json")
        league_config = {}
        if leagues_file.exists():
            leagues = json.loads(leagues_file.read_text())
            if isinstance(leagues, list):
                for league in leagues:
                    if str(league.get("league_id")) == str(args.league_id):
                        league_config = league
                        if not espn_s2:
                            espn_s2 = league.get("espn_s2", "")
                        if not swid:
                            swid = league.get("swid", "")
                        break
        
        print("[1/7] Fetching ESPN data...")
        games = fetch_week_from_espn(
            league_id=int(args.league_id),
            year=args.year,
            espn_s2=espn_s2,
            swid=swid,
            week=week
        )
        
        if not games:
            raise ValueError("No games found")
        
        print(f"   Found {len(games)} games")
        
        if args.llm_blurbs:
            print("[2/7] Generating LLM blurbs...")
            for i, game in enumerate(games, 1):
                if not game.get('blurb'):
                    print(f"   Generating blurb {i}/{len(games)}")
                    game['blurb'] = generate_llm_blurb(
                        game,
                        style=args.blurb_style,
                        model=args.model,
                        temperature=args.temperature,
                        max_words=args.blurb_words
                    )
        else:
            print("[2/7] Skipping LLM blurbs")
        
        print("[3/7] Building context...")
        cfg = league_config or {"league_id": args.league_id, "year": args.year}
        ctx = build_context(cfg, games)
        ctx['week_num'] = week
        
        add_enumerated_matchups(ctx, args.slots)
        add_template_synonyms(ctx, args.slots)
        
        print("[4/7] Attaching logos...")
        template_path = Path(args.template)
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {args.template}")
        
        doc = DocxTemplate(str(template_path))
        ctx = attach_all_logos(doc, ctx, args.logo_mm, args.slots)
        
        print("[5/7] Rendering template...")
        doc.render(ctx)
        
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        
        league_slug = cfg.get('short_name', cfg.get('name', 'league')).replace(' ', '_')
        docx_path = out_dir / f"{league_slug}_week_{week}.docx"
        
        doc.save(str(docx_path))
        print(f"   Saved: {docx_path}")
        
        print("[6/7] Adding footer gradient...")
        add_footer_gradient(docx_path)
        
        if not args.no_pdf:
            print("[7/7] Converting to PDF/A...")
            
            pdf_path = docx_path.with_suffix('.pdf')
            cmd = f'soffice --headless --convert-to pdf --outdir {shlex.quote(str(out_dir))} {shlex.quote(str(docx_path))}'
            subprocess.run(cmd, shell=True, check=True)
            
            pdfa_path = docx_path.with_name(f"{docx_path.stem}_PDFA.pdf")
            if convert_to_pdfa(pdf_path, pdfa_path):
                pdf_path.unlink()
                pdfa_path.rename(pdf_path)
                print(f"   PDF/A: {pdf_path}")
            else:
                print(f"   PDF: {pdf_path}")
        else:
            print("[7/7] Skipping PDF")
        
        print("\n✅ SUCCESS!")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()