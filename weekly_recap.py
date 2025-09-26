#!/usr/bin/env python3
"""
Weekly Recap Builder for Gridiron Gazette - HTML/PDF VERSION
Generates HTML from Jinja2 template and converts to PDF
"""
from __future__ import annotations
import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, List

# HTML/PDF generation
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML, CSS

import gazette_data
from storymaker import (
    StoryMaker, 
    MatchupData, 
    PlayerStat,
    clean_markdown_for_docx,
    clean_all_markdown_in_dict
)

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Optional OpenAI wrapper
try:
    from llm_openai import chat as openai_llm
except Exception:
    openai_llm = None
    logger.info("OpenAI LLM not available, will use fallback templates")


def build_weekly_recap(
    league_id: int,
    year: int,
    week: Optional[int] = None,
    template: str = "templates/recap_template.html",
    output_path: str = "recaps/Gazette_{year}_W{week02}.pdf",
    use_llm_blurbs: bool = True,
) -> str:
    """
    Builds the Gazette PDF from HTML template:
      1) Fetches ESPN context
      2) Generates Sabre recaps
      3) Cleans markdown
      4) Renders HTML template
      5) Converts to PDF
    
    Args:
        league_id: ESPN league ID
        year: Season year
        week: Week number (None for current week)
        template: Path to HTML template
        output_path: Output path pattern
        use_llm_blurbs: Whether to use LLM for Sabre blurbs
    """
    # Get base context from ESPN
    ctx = gazette_data.build_context(league_id, year, week)
    
    # Use the week from context if not provided
    if week is None:
        week = ctx.get("WEEK_NUMBER", ctx.get("WEEK", 1))
    
    # Add Sabre blurbs
    if use_llm_blurbs:
        _attach_sabre_recaps(ctx)
    else:
        _attach_simple_blurbs(ctx)
    
    # Add team logos from team_logos.json
    _attach_team_logos(ctx)
    
    # Clean all markdown from the context
    ctx = clean_all_markdown_in_dict(ctx)
    
    # Render HTML and convert to PDF
    out = _render_html_to_pdf(template, output_path, ctx)
    
    logger.info(f"✅ Generated PDF gazette: {out}")
    return out


def _render_html_to_pdf(template_path: str, output_pattern: str, ctx: Dict[str, Any]) -> str:
    """Render HTML template and convert to PDF using WeasyPrint"""
    
    from weasyprint import HTML, CSS
    from jinja2 import Environment, FileSystemLoader
    
    tpl_path = Path(template_path)
    if not tpl_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    
    # Get week and year for output filename
    week = int(ctx.get("WEEK_NUMBER", ctx.get("WEEK", 0)))
    year = ctx.get("YEAR", "")
    
    # Format output path
    output_path = output_pattern.format(
        year=year,
        week=week,
        week02=f"{week:02d}"
    )
    
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Set up Jinja2 environment
    template_dir = tpl_path.parent if tpl_path.parent.exists() else Path('.')
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template(tpl_path.name)
    
    # Render HTML
    html_content = template.render(**ctx)
    
    # Convert to PDF with WeasyPrint
    HTML(string=html_content).write_pdf(str(output_file))
    logger.info(f"✅ Generated PDF: {output_file}")
    
    return str(output_file)


def _attach_team_logos(ctx: Dict[str, Any]) -> None:
    """Attach team logo paths from team_logos.json"""
    
    logo_file = Path("team_logos.json")
    if not logo_file.exists():
        logger.warning("team_logos.json not found, skipping logos")
        return
    
    try:
        with open(logo_file, 'r', encoding='utf-8') as f:
            logo_mappings = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load team_logos.json: {e}")
        return
    
    # Add league and sponsor logos if present
    if "LEAGUE_LOGO" in logo_mappings:
        logo_path = Path(logo_mappings["LEAGUE_LOGO"])
        if logo_path.exists():
            ctx["LEAGUE_LOGO"] = str(logo_path.resolve())
        else:
            ctx["LEAGUE_LOGO"] = ctx.get("LEAGUE_NAME", "")
    
    if "SPONSOR_LOGO" in logo_mappings:
        logo_path = Path(logo_mappings["SPONSOR_LOGO"])
        if logo_path.exists():
            ctx["SPONSOR_LOGO"] = str(logo_path.resolve())
    
    # Add team logos for each matchup
    count = ctx.get("MATCHUP_COUNT", 7)
    for i in range(1, min(count + 1, 11)):
        home_team = ctx.get(f"MATCHUP{i}_HOME")
        away_team = ctx.get(f"MATCHUP{i}_AWAY")
        
        if home_team and home_team in logo_mappings:
            logo_path = Path(logo_mappings[home_team])
            if logo_path.exists():
                ctx[f"MATCHUP{i}_HOME_LOGO"] = str(logo_path.resolve())
            else:
                logger.warning(f"Logo file not found for {home_team}: {logo_path}")
                ctx[f"MATCHUP{i}_HOME_LOGO"] = ""
        else:
            ctx[f"MATCHUP{i}_HOME_LOGO"] = ""
        
        if away_team and away_team in logo_mappings:
            logo_path = Path(logo_mappings[away_team])
            if logo_path.exists():
                ctx[f"MATCHUP{i}_AWAY_LOGO"] = str(logo_path.resolve())
            else:
                logger.warning(f"Logo file not found for {away_team}: {logo_path}")
                ctx[f"MATCHUP{i}_AWAY_LOGO"] = ""
        else:
            ctx[f"MATCHUP{i}_AWAY_LOGO"] = ""


def _attach_sabre_recaps(ctx: Dict[str, Any]) -> None:
    """Generate and attach Sabre recaps using the StoryMaker"""
    
    maker = StoryMaker(llm=openai_llm if os.getenv("OPENAI_API_KEY") else None)
    
    count = int(ctx.get("MATCHUP_COUNT", 7))
    league_name = str(ctx.get("LEAGUE_NAME", "League"))
    week_num = int(ctx.get("WEEK_NUMBER", ctx.get("WEEK", 0)))
    
    for i in range(1, min(count + 1, 11)):
        home = ctx.get(f"MATCHUP{i}_HOME")
        away = ctx.get(f"MATCHUP{i}_AWAY")
        home_score = ctx.get(f"MATCHUP{i}_HS")
        away_score = ctx.get(f"MATCHUP{i}_AS")
        
        if not (home and away):
            continue
        
        # Get top performers
        top_performers = []
        top_home = ctx.get(f"MATCHUP{i}_TOP_HOME", "")
        top_away = ctx.get(f"MATCHUP{i}_TOP_AWAY", "")
        
        if top_home:
            top_performers.append(PlayerStat(name=top_home, team=home))
        if top_away:
            top_performers.append(PlayerStat(name=top_away, team=away))
        
        # Parse scores
        try:
            score_a = float(home_score) if home_score else 0.0
            score_b = float(away_score) if away_score else 0.0
        except (ValueError, TypeError):
            score_a = score_b = 0.0
        
        # Create matchup data
        matchup_data = MatchupData(
            league_name=league_name,
            week=week_num,
            team_a=str(home),
            team_b=str(away),
            score_a=score_a,
            score_b=score_b,
            top_performers=top_performers,
            winner=str(home) if score_a >= score_b else str(away),
            margin=abs(score_a - score_b),
        )
        
        # Generate recap with markdown cleaning
        recap = maker.generate_recap(matchup_data, clean_markdown=True)
        
        # Format for HTML display
        paragraphs = recap.split('\n\n')
        cleaned_paragraphs = [p.strip() for p in paragraphs if p.strip()]
        recap = '\n\n'.join(cleaned_paragraphs)
        
        ctx[f"MATCHUP{i}_BLURB"] = recap
        
        logger.info(f"Generated Sabre recap for matchup {i}: {home} vs {away}")


def _attach_simple_blurbs(ctx: Dict[str, Any]) -> None:
    """Attach simple fallback blurbs when LLM is not available"""
    
    count = int(ctx.get("MATCHUP_COUNT", 7))
    
    for i in range(1, min(count + 1, 11)):
        if ctx.get(f"MATCHUP{i}_BLURB"):
            continue
            
        home = ctx.get(f"MATCHUP{i}_HOME")
        away = ctx.get(f"MATCHUP{i}_AWAY")
        home_score = ctx.get(f"MATCHUP{i}_HS")
        away_score = ctx.get(f"MATCHUP{i}_AS")
        
        if not (home and away):
            continue
        
        try:
            score_a = float(home_score) if home_score else 0.0
            score_b = float(away_score) if away_score else 0.0
        except (ValueError, TypeError):
            score_a = score_b = 0.0
        
        winner = home if score_a >= score_b else away
        loser = away if winner == home else home
        margin = abs(score_a - score_b)
        
        if margin < 5:
            tone = "nail-biter"
        elif margin > 30:
            tone = "absolute demolition"
        elif margin > 20:
            tone = "statement win"
        else:
            tone = "solid victory"
        
        blurb = f"In a {tone}, {winner} topped {loser} {home_score}-{away_score}. "
        
        if margin < 5:
            blurb += "This one came down to the wire, with every decision mattering in the final outcome. "
        elif margin > 30:
            blurb += f"{loser} might want to forget this one ever happened. "
        else:
            blurb += f"{winner} controlled the game and earned the W. "
        
        blurb += "\n\n—Sabre, your hilariously snarky 4-legged Gridiron Gazette reporter 🐾"
        
        ctx[f"MATCHUP{i}_BLURB"] = clean_markdown_for_docx(blurb)


def verify_setup():
    """Verify that everything is set up correctly"""
    
    print("\n" + "="*60)
    print("GRIDIRON GAZETTE SETUP VERIFICATION")
    print("="*60)
    
    all_good = True
    
    # Check for template
    template_paths = [
        Path("templates/recap_template.html"),
        Path("recap_template.html"),
    ]
    
    template_found = False
    for path in template_paths:
        if path.exists():
            print(f"✅ Template found: {path}")
            template_found = True
            break
    
    if not template_found:
        print("❌ Template not found! Save recap_template.html in templates/ directory")
        all_good = False
    
    # Check for team_logos.json
    if Path("team_logos.json").exists():
        print("✅ team_logos.json found")
        
        # Verify logo files
        with open("team_logos.json", 'r') as f:
            logos = json.load(f)
        
        missing = []
        for team, path in logos.items():
            if not Path(path).exists():
                missing.append(f"  - {path} (for {team})")
        
        if missing:
            print(f"⚠️  Missing {len(missing)} logo files:")
            for m in missing[:5]:  # Show first 5
                print(m)
            if len(missing) > 5:
                print(f"  ... and {len(missing)-5} more")
    else:
        print("⚠️  team_logos.json not found (logos will be skipped)")
        all_good = False
    
    # Check for required Python packages
    try:
        import jinja2
        print("✅ Jinja2 is installed")
    except:
        print("❌ Jinja2 not installed: pip install jinja2")
        all_good = False
    
    print("="*60)
    if all_good:
        print("✅ Everything looks good! Ready to generate gazettes.")
    else:
        print("❌ Some issues need to be fixed before running.")
    print("="*60)
    
    return all_good


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        verify_setup()
    else:
        print("Weekly Recap Builder - HTML/PDF Version")
        print("This module is called by build_gazette.py")
        print("\nTo verify setup: python weekly_recap.py verify")