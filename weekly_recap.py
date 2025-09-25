"""
Weekly Recap Builder for Gridiron Gazette
Generates the final DOCX output with all data, logos, and Sabre's commentary
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from docxtpl import DocxTemplate

# Import our modules
from storymaker import generate_sabre_blurbs, generate_spotlight_content, clean_markdown_for_docx
from logo_resolver import LogoResolver

log = logging.getLogger("weekly_recap")

# ================= Configuration =================

DEFAULT_TEMPLATE = "recap_template.docx"
DEFAULT_OUTPUT_DIR = "./output"

# ================= Context Enhancement =================

def enhance_context_with_blurbs(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add Sabre blurbs and spotlight content to the context
    """
    log.info("Enhancing context with Sabre blurbs...")
    
    # Generate main Sabre blurbs for each matchup
    try:
        blurbs = generate_sabre_blurbs(context)
        
        # Add blurbs to context with proper keys
        for matchup_num, blurb_text in blurbs.items():
            # Clean markdown from the blurb
            clean_blurb = clean_markdown_for_docx(blurb_text)
            
            # Add as both numbered and matchup-specific keys
            context[f"blurb_{matchup_num}"] = clean_blurb
            context[f"MATCHUP{matchup_num}_BLURB"] = clean_blurb
            
            log.info(f"Added blurb for matchup {matchup_num}")
    except Exception as e:
        log.error(f"Error generating Sabre blurbs: {e}")
    
    # Generate spotlight content (TOP_HOME, TOP_AWAY, etc.)
    try:
        spotlights = generate_spotlight_content(context)
        
        for key, value in spotlights.items():
            # Clean markdown from spotlight content
            clean_value = clean_markdown_for_docx(value)
            context[key] = clean_value
            
            log.info(f"Added spotlight: {key}")
    except Exception as e:
        log.error(f"Error generating spotlight content: {e}")
    
    return context

def add_logos_to_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve and add all logo paths to the context
    """
    log.info("Resolving logos...")
    
    resolver = LogoResolver()
    
    # Resolve team logos for each matchup
    for i in range(1, 8):
        home_key = f"MATCHUP{i}_HOME"
        away_key = f"MATCHUP{i}_AWAY"
        
        if home_key in context:
            home_team = context[home_key]
            home_logo = resolver.resolve_team_logo(home_team)
            if home_logo:
                context[f"MATCHUP{i}_HOME_LOGO"] = home_logo
                log.info(f"Found logo for {home_team}: {home_logo}")
        
        if away_key in context:
            away_team = context[away_key]
            away_logo = resolver.resolve_team_logo(away_team)
            if away_logo:
                context[f"MATCHUP{i}_AWAY_LOGO"] = away_logo
                log.info(f"Found logo for {away_team}: {away_logo}")
    
    # Resolve league logo
    league_name = context.get("LEAGUE_NAME", "")
    
    # Special handling for Browns league
    if "browns" in league_name.lower() or not league_name:
        # Direct path to brownseakc.png
        special_path = "./logos/team_logos/brownseakc.png"
        if os.path.exists(special_path):
            context["LEAGUE_LOGO"] = special_path
            log.info(f"Using Browns league logo: {special_path}")
        else:
            log.warning(f"Browns logo not found at: {special_path}")
    else:
        league_logo = resolver.resolve_league_logo(league_name)
        if league_logo:
            context["LEAGUE_LOGO"] = league_logo
            log.info(f"Found league logo: {league_logo}")
    
    # Resolve sponsor logo
    sponsor_name = context.get("SPONSOR_NAME", "Gridiron Gazette")
    sponsor_logo = resolver.resolve_sponsor_logo(sponsor_name)
    if sponsor_logo:
        context["SPONSOR_LOGO"] = sponsor_logo
        log.info(f"Found sponsor logo: {sponsor_logo}")
    
    return context

def add_awards_to_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format awards for the template
    """
    log.info("Formatting awards...")
    
    # Cupcake Award (lowest score)
    cupcake = context.get("CUPCAKE", "")
    if cupcake:
        cupcake_score = context.get("CUPCAKE_SCORE", "")
        context["CUPCAKE_AWARD"] = f"{cupcake} ({cupcake_score} pts)" if cupcake_score else cupcake
    else:
        context["CUPCAKE_AWARD"] = "---"
    
    # Kitty Award (closest loss)
    kitty = context.get("KITTY", "")
    if kitty:
        kitty_margin = context.get("KITTY_MARGIN", "")
        context["KITTY_AWARD"] = f"{kitty} (lost by {kitty_margin} pts)" if kitty_margin else kitty
    else:
        context["KITTY_AWARD"] = "---"
    
    # Top Score Award
    top_score = context.get("TOPSCORE", "")
    if top_score:
        top_score_pts = context.get("TOPSCORE_POINTS", "")
        context["TOPSCORE_AWARD"] = f"{top_score} ({top_score_pts} pts)" if top_score_pts else top_score
    else:
        context["TOPSCORE_AWARD"] = "---"
    
    return context

def validate_context(context: Dict[str, Any]) -> bool:
    """
    Validate that the context has required data
    """
    required_keys = [
        "WEEK",
        "YEAR", 
        "MATCHUP1_HOME",
        "MATCHUP1_AWAY",
        "MATCHUP1_HS",
        "MATCHUP1_AS"
    ]
    
    missing = []
    for key in required_keys:
        if key not in context or not context[key]:
            missing.append(key)
    
    if missing:
        log.warning(f"Missing required context keys: {missing}")
        return False
    
    return True

# ================= Template Rendering =================

def render_template(context: Dict[str, Any], 
                    template_path: str = DEFAULT_TEMPLATE,
                    output_path: str = None) -> str:
    """
    Render the DOCX template with the context data
    
    Returns:
        Path to the generated file
    """
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template not found: {template_path}")
    
    # Enhance context with all data
    context = enhance_context_with_blurbs(context)
    context = add_logos_to_context(context)
    context = add_awards_to_context(context)
    
    # Validate context
    if not validate_context(context):
        log.warning("Context validation failed, but continuing...")
    
    # Generate output filename if not provided
    if not output_path:
        week = context.get("WEEK", "X")
        year = context.get("YEAR", datetime.now().year)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"Gazette_Week{week}_{year}_{timestamp}.docx"
        
        os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(DEFAULT_OUTPUT_DIR, output_filename)
    
    # Render the template
    try:
        doc = DocxTemplate(template_path)
        
        # Clean all text fields of markdown before rendering
        for key, value in context.items():
            if isinstance(value, str) and any(marker in str(value) for marker in ['**', '*', '__', '_', '`', '##']):
                context[key] = clean_markdown_for_docx(value)
        
        doc.render(context)
        doc.save(output_path)
        
        log.info(f"✅ Generated recap: {output_path}")
        return output_path
        
    except Exception as e:
        log.error(f"Error rendering template: {e}")
        raise

# ================= Main Entry Point =================

def build_recap(context: Dict[str, Any], 
               template_path: str = DEFAULT_TEMPLATE,
               output_path: str = None,
               use_llm: bool = True) -> str:
    """
    Main entry point for building a weekly recap
    
    Args:
        context: Data context from gazette_data
        template_path: Path to DOCX template
        output_path: Optional output path
        use_llm: Whether to use OpenAI for blurbs (default True)
    
    Returns:
        Path to generated file
    """
    log.info("="*60)
    log.info(f"Building Weekly Recap for Week {context.get('WEEK', '?')}")
    log.info("="*60)
    
    # Set flag for LLM usage
    if not use_llm:
        # Temporarily disable OpenAI
        os.environ['DISABLE_OPENAI'] = 'true'
    
    try:
        output_file = render_template(context, template_path, output_path)
        
        # Print summary
        log.info("\n" + "="*60)
        log.info("RECAP GENERATION COMPLETE")
        log.info("="*60)
        log.info(f"Week: {context.get('WEEK', '?')}")
        log.info(f"Year: {context.get('YEAR', '?')}")
        log.info(f"League: {context.get('LEAGUE_NAME', 'Unknown')}")
        log.info(f"Output: {output_file}")
        
        # Report on what was included
        has_blurbs = any(key.startswith("blurb_") for key in context)
        has_spotlights = any("_TOP_" in key for key in context)
        has_logos = any("_LOGO" in key for key in context)
        
        log.info("\nContent included:")
        log.info(f"  ✅ Matchup scores: Yes")
        log.info(f"  {'✅' if has_blurbs else '❌'} Sabre blurbs: {'Yes' if has_blurbs else 'No'}")
        log.info(f"  {'✅' if has_spotlights else '❌'} Stats spotlights: {'Yes' if has_spotlights else 'No'}")
        log.info(f"  {'✅' if has_logos else '❌'} Team logos: {'Yes' if has_logos else 'No'}")
        
        if context.get("LEAGUE_LOGO"):
            log.info(f"  ✅ League logo: {context['LEAGUE_LOGO']}")
        else:
            log.info(f"  ❌ League logo: Not found")
        
        log.info("="*60)
        
        return output_file
        
    finally:
        # Clean up temporary flag
        if not use_llm and 'DISABLE_OPENAI' in os.environ:
            del os.environ['DISABLE_OPENAI']

# ================= Testing =================

def test_with_sample_data():
    """Test with sample data"""
    sample_context = {
        "WEEK": 3,
        "YEAR": 2025,
        "LEAGUE_NAME": "Browns Fantasy League",
        
        # Sample matchup
        "MATCHUP1_HOME": "Thunder Hawks",
        "MATCHUP1_AWAY": "Lightning Bolts",
        "MATCHUP1_HS": 125.50,
        "MATCHUP1_AS": 98.75,
        "MATCHUP1_HOME_TOP_SCORER": "Josh Allen",
        "MATCHUP1_HOME_TOP_POINTS": 32.5,
        "MATCHUP1_AWAY_TOP_SCORER": "Justin Jefferson", 
        "MATCHUP1_AWAY_TOP_POINTS": 28.2,
        
        # Awards
        "CUPCAKE": "Team Disaster",
        "CUPCAKE_SCORE": 65.3,
        "KITTY": "Almost Winners",
        "KITTY_MARGIN": 0.5,
        "TOPSCORE": "Thunder Hawks",
        "TOPSCORE_POINTS": 125.50
    }
    
    print("Testing recap generation with sample data...")
    
    try:
        output_file = build_recap(sample_context, use_llm=False)
        print(f"✅ Test successful! Output: {output_file}")
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_with_sample_data()
    else:
        print("Weekly Recap Builder")
        print("This module is typically called from build_gazette.py")
        print("\nTo test with sample data:")
        print("  python weekly_recap.py test")