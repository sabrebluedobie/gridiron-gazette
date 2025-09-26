#!/usr/bin/env python3
"""
Weekly Recap Builder for Gridiron Gazette - HTML VERSION
COMPLETE VERSION using team_logos.json for all logo mappings
- Generates HTML from Jinja2 template
- Converts to PDF with proper layout control
- Embeds images using file paths for HTML img tags
- CSS handles all formatting and layout
- Supports multiple leagues via JSON
"""
from __future__ import annotations
import os
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, List

# HTML/PDF generation
from jinja2 import Environment, FileSystemLoader
import pdfkit

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

# Optional OpenAI wrapper (safe if absent)
try:
    from llm_openai import chat as openai_llm
except Exception:
    openai_llm = None
    logger.info("OpenAI LLM not available, will use fallback templates")


class LogoManager:
    """Manages logo mappings from team_logos.json"""
    
    def __init__(self, json_file: str = "team_logos.json"):
        """Initialize with logo mappings from JSON file"""
        self.logo_mappings = {}
        self.json_file = json_file
        self.load_mappings()
    
    def load_mappings(self):
        """Load logo mappings from JSON file"""
        json_path = Path(self.json_file)
        if json_path.exists():
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    self.logo_mappings = json.load(f)
                logger.info(f"✅ Loaded {len(self.logo_mappings)} logo mappings from {self.json_file}")
            except Exception as e:
                logger.error(f"Failed to load {self.json_file}: {e}")
                self.logo_mappings = {}
        else:
            logger.warning(f"Logo mappings file not found: {self.json_file}")
            self.logo_mappings = {}
    
    def get_team_logo(self, team_name: str) -> Optional[str]:
        """Get logo path for a team from mappings (returns path string for HTML)"""
        if team_name in self.logo_mappings:
            logo_path = Path(self.logo_mappings[team_name])
            if logo_path.exists():
                # Convert to absolute path for HTML img src
                return str(logo_path.resolve())
            else:
                logger.warning(f"Logo file not found: {logo_path} for team {team_name}")
        else:
            logger.warning(f"No mapping found for team: {team_name}")
        return None
    
    def get_league_logo(self) -> Optional[str]:
        """Get league logo from mappings (returns path string for HTML)"""
        if "LEAGUE_LOGO" in self.logo_mappings:
            logo_path = Path(self.logo_mappings["LEAGUE_LOGO"])
            if logo_path.exists():
                return str(logo_path.resolve())
            else:
                logger.warning(f"League logo file not found: {logo_path}")
        return None
    
    def get_sponsor_logo(self) -> Optional[str]:
        """Get sponsor logo from mappings (returns path string for HTML)"""
        if "SPONSOR_LOGO" in self.logo_mappings:
            logo_path = Path(self.logo_mappings["SPONSOR_LOGO"])
            if logo_path.exists():
                return str(logo_path.resolve())
            else:
                logger.warning(f"Sponsor logo file not found: {logo_path}")
        return None


def build_weekly_recap(
    league_id: int,
    year: int,
    week: int,
    template: str = "recap_template.html",  # Changed to HTML template
    output_path: str = "recaps/Gazette_{year}_W{week02}.pdf",  # Output PDF
    use_llm_blurbs: bool = True,
    logo_json: str = "team_logos.json"
) -> str:
    """
    Builds the Gazette PDF from HTML template with comprehensive fixes:
      1) Fetches ESPN context
      2) Generates Sabre recaps
      3) Prepares logo paths for HTML img tags
      4) Cleans markdown
      5) Renders HTML template
      6) Converts to PDF with precise layout control
    
    Args:
        league_id: ESPN league ID
        year: Season year
        week: Week number
        template: Path to HTML template
        output_path: Output path pattern
        use_llm_blurbs: Whether to use LLM for Sabre blurbs
        logo_json: Path to team_logos.json file
    """
    # Get base context from ESPN
    ctx = gazette_data.build_context(league_id, year, week)
    
    # Add Sabre blurbs
    if use_llm_blurbs:
        _attach_sabre_recaps(ctx)
    else:
        _attach_simple_blurbs(ctx)
    
    # Add spotlight content
    _attach_spotlight_content(ctx)
    
    # Clean all markdown from the context (keep this for text content)
    ctx = clean_all_markdown_in_dict(ctx)
    
    # Render HTML and convert to PDF
    out = _render_html_to_pdf(template, output_path, ctx, logo_json)
    
    logger.info(f"✅ Generated PDF gazette: {out}")
    return out


def _render_html_to_pdf(template_path: str, out_pattern: str, ctx: Dict[str, Any], logo_json: str) -> str:
    """
    Render the HTML template with proper image paths and convert to PDF.
    """
    tpl_path = Path(template_path)
    if not tpl_path.exists():
        raise FileNotFoundError(f"Template not found: {tpl_path}")

    # Prepare context with logo file paths for HTML
    image_context = _prepare_image_context_for_html(ctx.copy(), logo_json)
    
    # Get week number for output filename
    week = int(ctx.get("WEEK_NUMBER", 0) or ctx.get("WEEK", 0) or 0)
    year = ctx.get("YEAR", "")
    
    # Format output path
    out_path = out_pattern.format(
        year=year, 
        week=week, 
        week02=f"{week:02d}"
    )
    
    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Set up Jinja2 environment
    template_dir = tpl_path.parent if tpl_path.parent.exists() else Path('.')
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template(tpl_path.name)
    
    # Render HTML
    html_content = template.render(**image_context)
    
    # PDF conversion options for better layout control
    options = {
        'page-size': 'Letter',
        'orientation': 'Portrait',
        'margin-top': '0.75in',
        'margin-right': '0.5in',
        'margin-bottom': '0.75in',
        'margin-left': '0.5in',
        'encoding': 'UTF-8',
        'no-outline': None,
        'enable-local-file-access': None,  # Allow local images
        'print-media-type': None,  # Use print CSS
        'disable-smart-shrinking': None,  # Prevent content shrinking
        'dpi': 300,  # High quality images
        'image-quality': 100,
    }
    
    try:
        # Convert HTML to PDF
        pdfkit.from_string(html_content, str(out_file), options=options)
        logger.info(f"✅ Generated PDF gazette: {out_file}")
        _log_recap_summary(image_context, out_file)
        
    except Exception as e:
        logger.error(f"Failed to generate PDF: {e}")
        
        # Fallback: Save HTML for debugging
        html_debug_path = out_file.with_suffix('.html')
        with open(html_debug_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info(f"💾 Saved HTML for debugging: {html_debug_path}")
        raise
    
    return str(out_file)


def _prepare_image_context_for_html(context: Dict[str, Any], logo_json: str) -> Dict[str, Any]:
    """
    Convert logo mappings to file paths for HTML img src attributes.
    This replaces the DOCX InlineImage approach with simple file paths.
    """
    logger.info(f"Preparing image paths from {logo_json}...")
    
    # Initialize logo manager with JSON mappings
    logo_manager = LogoManager(logo_json)
    
    # Process team logos for each matchup
    images_found = 0
    for i in range(1, 8):
        home_key = f"MATCHUP{i}_HOME"
        away_key = f"MATCHUP{i}_AWAY"
        
        # Home team logo
        if home_key in context:
            team_name = context[home_key]
            logo_key = f"MATCHUP{i}_HOME_LOGO"
            
            logo_path = logo_manager.get_team_logo(team_name)
            if logo_path:
                context[logo_key] = logo_path
                logger.info(f"✅ Found logo for {team_name}: {logo_path}")
                images_found += 1
            else:
                context[logo_key] = ""
                logger.warning(f"No logo found for home team: {team_name}")
        
        # Away team logo
        if away_key in context:
            team_name = context[away_key]
            logo_key = f"MATCHUP{i}_AWAY_LOGO"
            
            logo_path = logo_manager.get_team_logo(team_name)
            if logo_path:
                context[logo_key] = logo_path
                logger.info(f"✅ Found logo for {team_name}: {logo_path}")
                images_found += 1
            else:
                context[logo_key] = ""
                logger.warning(f"No logo found for away team: {team_name}")
    
    # Process league logo
    league_logo_path = logo_manager.get_league_logo()
    if league_logo_path:
        context["LEAGUE_LOGO"] = league_logo_path
        logger.info(f"✅ Found league logo: {league_logo_path}")
        images_found += 1
    else:
        context["LEAGUE_LOGO"] = ""
        logger.warning("No league logo found in mappings")
    
    # Process sponsor logo
    sponsor_logo_path = logo_manager.get_sponsor_logo()
    if sponsor_logo_path:
        context["SPONSOR_LOGO"] = sponsor_logo_path
        logger.info(f"✅ Found sponsor logo: {sponsor_logo_path}")
        images_found += 1
    else:
        context["SPONSOR_LOGO"] = ""
        logger.warning("No sponsor logo found in mappings")
    
    logger.info(f"Total logo paths prepared: {images_found}")
    return context


def _attach_sabre_recaps(ctx: Dict[str, Any]) -> None:
    """Generate and attach Sabre recaps using the StoryMaker."""
    maker = StoryMaker(llm=openai_llm if os.getenv("OPENAI_API_KEY") else None)

    count = int(ctx.get("MATCHUP_COUNT") or 7)
    league_name = str(ctx.get("LEAGUE_NAME", "League"))
    week_num = int(ctx.get("WEEK_NUMBER", 0) or ctx.get("WEEK", 0) or 0)

    for i in range(1, min(count + 1, 8)):
        h = ctx.get(f"MATCHUP{i}_HOME")
        a = ctx.get(f"MATCHUP{i}_AWAY")
        hs = ctx.get(f"MATCHUP{i}_HS")
        as_ = ctx.get(f"MATCHUP{i}_AS")
        
        if not (h and a):
            continue

        # Get top performers
        tops = []
        th = _safe(ctx.get(f"MATCHUP{i}_TOP_HOME", ""))
        ta = _safe(ctx.get(f"MATCHUP{i}_TOP_AWAY", ""))
        if th:
            tops.append(PlayerStat(name=th))
        if ta:
            tops.append(PlayerStat(name=ta))

        try:
            sa = float(str(hs)) if hs not in (None, "") else 0.0
            sb = float(str(as_)) if as_ not in (None, "") else 0.0
        except Exception:
            sa, sb = 0.0, 0.0

        md = MatchupData(
            league_name=league_name,
            week=week_num,
            team_a=str(h), 
            team_b=str(a),
            score_a=sa, 
            score_b=sb,
            top_performers=tops,
            winner=str(h) if sa >= sb else str(a),
            margin=abs(sa - sb),
        )
        
        # Generate recap with markdown cleaning enabled
        recap = maker.generate_recap(md, clean_markdown=True)
        
        # Additional cleanup for HTML formatting
        recap = recap.replace('\r\n', '\n').replace('\r', '\n')
        
        # Ensure proper paragraph breaks for HTML
        paragraphs = recap.split('\n\n')
        cleaned_paragraphs = [p.strip() for p in paragraphs if p.strip()]
        recap = '\n\n'.join(cleaned_paragraphs)
        
        ctx[f"MATCHUP{i}_BLURB"] = recap
        
        logger.info(f"Generated Sabre recap for matchup {i}: {h} vs {a}")


def _attach_simple_blurbs(ctx: Dict[str, Any]) -> None:
    """Attach simple fallback blurbs when LLM is not available."""
    count = int(ctx.get("MATCHUP_COUNT") or 7)
    for i in range(1, min(count + 1, 8)):
        if ctx.get(f"MATCHUP{i}_BLURB"):
            continue
        h = ctx.get(f"MATCHUP{i}_HOME")
        a = ctx.get(f"MATCHUP{i}_AWAY")
        hs = ctx.get(f"MATCHUP{i}_HS")
        as_ = ctx.get(f"MATCHUP{i}_AS")
        
        if not (h and a):
            continue
            
        try:
            sa = float(str(hs)) if hs not in (None, "") else 0.0
            sb = float(str(as_)) if as_ not in (None, "") else 0.0
        except Exception:
            sa, sb = 0.0, 0.0
            
        winner = h if sa >= sb else a
        loser = a if winner == h else h
        margin = abs(sa - sb)
        
        tone = "nail-biter" if margin < 5 else ("statement win" if margin > 20 else "solid win")
        
        blurb = f"{winner} topped {loser} {hs}-{as_} in a {tone}.\n\n—Sabre, your hilariously snarky 4-legged Gridiron Gazette reporter 🐾"
        ctx[f"MATCHUP{i}_BLURB"] = clean_markdown_for_docx(blurb)


def _attach_spotlight_content(ctx: Dict[str, Any]) -> None:
    """
    Generate additional spotlight content for Stats Spotlight sections.
    """
    count = int(ctx.get("MATCHUP_COUNT") or 7)
    
    for i in range(1, min(count + 1, 8)):
        h = ctx.get(f"MATCHUP{i}_HOME")
        a = ctx.get(f"MATCHUP{i}_AWAY")
        
        if not (h and a):
            continue
        
        # Fill in missing spotlight fields with Sabre-style content
        if not ctx.get(f"MATCHUP{i}_TOP_HOME"):
            ctx[f"MATCHUP{i}_TOP_HOME"] = f"{h}'s offense showed up when it mattered"
        
        if not ctx.get(f"MATCHUP{i}_TOP_AWAY"):
            ctx[f"MATCHUP{i}_TOP_AWAY"] = f"{a}'s squad battled to the end"
        
        if not ctx.get(f"MATCHUP{i}_BUST"):
            ctx[f"MATCHUP{i}_BUST"] = "Both teams had players who'd rather forget this week"
        
        if not ctx.get(f"MATCHUP{i}_KEYPLAY"):
            ctx[f"MATCHUP{i}_KEYPLAY"] = "Every yard was earned in this matchup"
        
        if not ctx.get(f"MATCHUP{i}_DEF"):
            ctx[f"MATCHUP{i}_DEF"] = "Defense wasn't invited to this scoring party"


def _log_recap_summary(ctx: Dict[str, Any], output_file: Path) -> None:
    """Log a summary of what was included in the recap."""
    logger.info("\n" + "="*60)
    logger.info("RECAP GENERATION SUMMARY")
    logger.info("="*60)
    logger.info(f"Week: {ctx.get('WEEK_NUMBER', '?')}")
    logger.info(f"Year: {ctx.get('YEAR', '?')}")
    logger.info(f"League: {ctx.get('LEAGUE_NAME', 'Unknown')}")
    logger.info(f"Output: {output_file}")
    
    # Count logo paths found
    image_count = sum(1 for key in ctx if 'LOGO' in key and ctx[key] and ctx[key] != "")
    
    logger.info(f"\n✅ Logo paths prepared: {image_count}")
    logger.info("✅ Using team_logos.json for all mappings")
    logger.info("✅ CSS handles layout and formatting")
    logger.info("✅ PDF generated with precise control")
    logger.info("="*60 + "\n")


def _safe(s: Any) -> str:
    """Safely convert any value to string."""
    return "" if s is None else str(s)


# Utility function to verify team_logos.json
def verify_logo_mappings(json_file: str = "team_logos.json"):
    """Verify that all logo files in team_logos.json exist"""
    print("\n" + "="*60)
    print(f"VERIFYING LOGO MAPPINGS IN {json_file}")
    print("="*60)
    
    if not Path(json_file).exists():
        print(f"❌ {json_file} not found!")
        return False
    
    manager = LogoManager(json_file)
    
    all_good = True
    missing_files = []
    
    for team, path in manager.logo_mappings.items():
        if Path(path).exists():
            print(f"✅ {team:30} -> {path}")
        else:
            print(f"❌ {team:30} -> {path} (FILE NOT FOUND)")
            missing_files.append((team, path))
            all_good = False
    
    if missing_files:
        print("\n⚠️ MISSING FILES:")
        for team, path in missing_files:
            print(f"  - {path} (for {team})")
        print("\nPlease ensure these files exist before running the gazette.")
    else:
        print("\n✅ All logo files found! Ready to generate gazette.")
    
    return all_good


def check_dependencies():
    """Check that required packages are installed"""
    missing = []
    
    try:
        import jinja2
    except ImportError:
        missing.append("jinja2")
    
    try:
        import pdfkit
    except ImportError:
        missing.append("pdfkit")
    
    if missing:
        print(f"❌ Missing required packages: {', '.join(missing)}")
        print("Install with: pip install " + " ".join(missing))
        return False
    
    # Check for wkhtmltopdf
    try:
        pdfkit.configuration()
    except Exception as e:
        print("❌ wkhtmltopdf not found. Install it:")
        print("  - Windows: Download from https://wkhtmltopdf.org/downloads.html")
        print("  - Mac: brew install wkhtmltopdf")
        print("  - Linux: sudo apt-get install wkhtmltopdf")
        return False
    
    print("✅ All dependencies are available")
    return True


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        verify_logo_mappings()
    elif len(sys.argv) > 1 and sys.argv[1] == "deps":
        check_dependencies()
    else:
        print("Weekly Recap Builder - HTML/PDF VERSION")
        print("Features:")
        print("  ✅ Generates HTML from Jinja2 template")
        print("  ✅ Converts to PDF with precise layout")
        print("  ✅ Loads logos from team_logos.json")
        print("  ✅ CSS handles all formatting")
        print("  ✅ No more layout shift issues")
        print("\nUsage:")
        print("  Called from build_gazette.py")
        print("  Or verify logos: python weekly_recap.py verify")
        print("  Or check deps: python weekly_recap.py deps")