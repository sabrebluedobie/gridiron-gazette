#!/usr/bin/env python3
from __future__ import annotations
import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from docx import Document
from docx.text.paragraph import Paragraph

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

# Optional OpenAI wrapper (safe if absent)
try:
    from llm_openai import chat as openai_llm
except Exception:
    openai_llm = None
    logger.info("OpenAI LLM not available, will use fallback templates")

# Optional logo resolver
try:
    from logo_resolver import LogoResolver
    logo_resolver_available = True
except ImportError:
    logo_resolver_available = False
    logger.info("Logo resolver not available")


def build_weekly_recap(
    league_id: int,
    year: int,
    week: int,
    template: str = "recap_template.docx",
    output_path: str = "recaps/Gazette_{year}_W{week02}.docx",
    use_llm_blurbs: bool = True,
) -> str:
    """
    Builds the Gazette docx by:
      1) fetching ESPN context (fills ALL template tokens),
      2) generating Sabre recaps into MATCHUP{i}_BLURB,
      3) adding logos if available,
      4) cleaning markdown from all text,
      5) rendering {{ TOKEN }} placeholders.
    """
    # Get base context from ESPN
    ctx = gazette_data.build_context(league_id, year, week)
    
    # Add Sabre blurbs
    if use_llm_blurbs:
        _attach_sabre_recaps(ctx)
    else:
        _attach_simple_blurbs(ctx)
    
    # Add logos if resolver is available
    if logo_resolver_available:
        _attach_logos(ctx)
    
    # Add spotlight content
    _attach_spotlight_content(ctx)
    
    # Clean all markdown from the context
    ctx = clean_all_markdown_in_dict(ctx)
    
    # Render the doc
    out = _render_docx(template, output_path, ctx)
    return out


def _attach_sabre_recaps(ctx: Dict[str, Any]) -> None:
    """Generate and attach Sabre recaps using the StoryMaker."""
    maker = StoryMaker(llm=openai_llm if os.getenv("OPENAI_API_KEY") else None)

    count = int(ctx.get("MATCHUP_COUNT") or 7)
    league_name = str(ctx.get("LEAGUE_NAME", "League"))
    week_num = int(ctx.get("WEEK_NUMBER", 0) or ctx.get("WEEK", 0) or 0)

    for i in range(1, min(count, 7) + 1):
        h = ctx.get(f"MATCHUP{i}_HOME")
        a = ctx.get(f"MATCHUP{i}_AWAY")
        hs = ctx.get(f"MATCHUP{i}_HS")
        as_ = ctx.get(f"MATCHUP{i}_AS")
        
        if not (h and a):
            continue

        # Grow optional "top performers" for extra flavor
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
        ctx[f"MATCHUP{i}_BLURB"] = recap
        
        logger.info(f"Generated Sabre recap for matchup {i}: {h} vs {a}")


def _attach_simple_blurbs(ctx: Dict[str, Any]) -> None:
    """Attach simple fallback blurbs when LLM is not available."""
    count = int(ctx.get("MATCHUP_COUNT") or 7)
    for i in range(1, min(count, 7) + 1):
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
    Uses Sabre's voice for TOP_HOME, TOP_AWAY, BUST, KEYPLAY, and DEF fields.
    """
    maker = StoryMaker(llm=openai_llm if os.getenv("OPENAI_API_KEY") else None)
    
    count = int(ctx.get("MATCHUP_COUNT") or 7)
    league_name = str(ctx.get("LEAGUE_NAME", "League"))
    week_num = int(ctx.get("WEEK_NUMBER", 0) or ctx.get("WEEK", 0) or 0)
    
    for i in range(1, min(count, 7) + 1):
        h = ctx.get(f"MATCHUP{i}_HOME")
        a = ctx.get(f"MATCHUP{i}_AWAY")
        
        if not (h and a):
            continue
        
        # If these spotlight fields are empty, generate witty one-liners
        if not ctx.get(f"MATCHUP{i}_TOP_HOME"):
            # Use existing top scorer info if available
            top_home = ctx.get(f"MATCHUP{i}_HOME_TOP_SCORER", "")
            top_home_pts = ctx.get(f"MATCHUP{i}_HOME_TOP_POINTS", "")
            if top_home:
                ctx[f"MATCHUP{i}_TOP_HOME"] = f"{top_home} carried the squad with {top_home_pts} points"
            else:
                ctx[f"MATCHUP{i}_TOP_HOME"] = f"{h}'s offense showed up when it mattered"
        
        if not ctx.get(f"MATCHUP{i}_TOP_AWAY"):
            top_away = ctx.get(f"MATCHUP{i}_AWAY_TOP_SCORER", "")
            top_away_pts = ctx.get(f"MATCHUP{i}_AWAY_TOP_POINTS", "")
            if top_away:
                ctx[f"MATCHUP{i}_TOP_AWAY"] = f"{top_away} led the charge with {top_away_pts} points"
            else:
                ctx[f"MATCHUP{i}_TOP_AWAY"] = f"{a}'s squad battled to the end"
        
        if not ctx.get(f"MATCHUP{i}_BUST"):
            ctx[f"MATCHUP{i}_BUST"] = "Both teams had players who'd rather forget this week"
        
        if not ctx.get(f"MATCHUP{i}_KEYPLAY"):
            ctx[f"MATCHUP{i}_KEYPLAY"] = "Every yard was earned in this matchup"
        
        if not ctx.get(f"MATCHUP{i}_DEF"):
            ctx[f"MATCHUP{i}_DEF"] = "Defense wasn't invited to this scoring party"


def _attach_logos(ctx: Dict[str, Any]) -> None:
    """
    Resolve and attach logo paths using the LogoResolver.
    Handles team logos, league logo, and sponsor logo.
    """
    resolver = LogoResolver()
    
    # Resolve team logos for each matchup
    count = int(ctx.get("MATCHUP_COUNT") or 7)
    for i in range(1, min(count, 7) + 1):
        home_key = f"MATCHUP{i}_HOME"
        away_key = f"MATCHUP{i}_AWAY"
        
        if home_key in ctx:
            home_team = ctx[home_key]
            home_logo = resolver.resolve_team_logo(home_team)
            if home_logo:
                ctx[f"MATCHUP{i}_HOME_LOGO"] = home_logo
                logger.info(f"Found logo for {home_team}: {home_logo}")
        
        if away_key in ctx:
            away_team = ctx[away_key]
            away_logo = resolver.resolve_team_logo(away_team)
            if away_logo:
                ctx[f"MATCHUP{i}_AWAY_LOGO"] = away_logo
                logger.info(f"Found logo for {away_team}: {away_logo}")
    
    # Resolve league logo with special handling for Browns
    league_name = ctx.get("LEAGUE_NAME", "")
    
    # Check for Browns league specifically
    browns_logo_paths = [
        "./logos/team_logos/brownseakc.png",
        "./logos/league_logos/brownseakc.png",
        "./logos/brownseakc.png",
        "brownseakc.png"
    ]
    
    logo_found = False
    for path in browns_logo_paths:
        if os.path.exists(path):
            ctx["LEAGUE_LOGO"] = path
            logger.info(f"Found Browns league logo at: {path}")
            logo_found = True
            break
    
    if not logo_found:
        # Try standard league logo resolution
        league_logo = resolver.resolve_league_logo(league_name)
        if league_logo:
            ctx["LEAGUE_LOGO"] = league_logo
            logger.info(f"Found league logo: {league_logo}")
        else:
            logger.warning(f"No league logo found for: {league_name}")
    
    # Resolve sponsor logo
    sponsor_name = ctx.get("SPONSOR_NAME", "Gridiron Gazette")
    sponsor_logo = resolver.resolve_sponsor_logo(sponsor_name)
    if sponsor_logo:
        ctx["SPONSOR_LOGO"] = sponsor_logo
        logger.info(f"Found sponsor logo: {sponsor_logo}")


def _render_docx(template_path: str, out_pattern: str, ctx: Dict[str, Any]) -> str:
    """
    Render the DOCX template with the provided context.
    All markdown should already be cleaned from the context.
    """
    tpl = Path(template_path)
    if not tpl.exists():
        raise FileNotFoundError(f"Template not found: {tpl}")

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

    # Load document
    doc = Document(str(tpl))
    
    # Build replacements dictionary with double braces
    replacements = {f"{{{{ {k} }}}}": str(v) for k, v in ctx.items()}
    
    # Also add single brace versions for compatibility
    replacements.update({f"{{ {k} }}": str(v) for k, v in ctx.items()})
    
    # Perform replacements
    _replace_in_document(doc, replacements)
    
    # Save the document
    doc.save(str(out_file))
    
    logger.info(f"✅ Generated recap document: {out_file}")
    
    # Log what content was included
    _log_recap_summary(ctx, out_file)
    
    return str(out_file)


def _replace_in_document(doc: Document, replacements: Dict[str, str]) -> None:
    """
    Replace all placeholders in the document with their values.
    Handles both paragraphs and tables.
    """
    def replace_in_paragraph(p: Paragraph) -> None:
        if not p.runs:
            return
        
        # Combine all runs to get full text
        text = "".join(run.text for run in p.runs)
        orig = text
        
        # Perform all replacements
        for placeholder, value in replacements.items():
            if placeholder in text:
                text = text.replace(placeholder, value)
                logger.debug(f"Replaced {placeholder} in paragraph")
        
        # If text changed, update the paragraph
        if text != orig:
            # Clear existing runs
            while p.runs:
                p.runs[0].clear()
                p.runs[0].text = ""
                p._element.remove(p.runs[0]._element)
            # Add new text as single run
            p.add_run(text)

    # Replace in all paragraphs
    for p in doc.paragraphs:
        replace_in_paragraph(p)
    
    # Replace in all tables
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    replace_in_paragraph(p)


def _log_recap_summary(ctx: Dict[str, Any], output_file: Path) -> None:
    """Log a summary of what was included in the recap."""
    logger.info("\n" + "="*60)
    logger.info("RECAP GENERATION SUMMARY")
    logger.info("="*60)
    logger.info(f"Week: {ctx.get('WEEK_NUMBER', '?')}")
    logger.info(f"Year: {ctx.get('YEAR', '?')}")
    logger.info(f"League: {ctx.get('LEAGUE_NAME', 'Unknown')}")
    logger.info(f"Output: {output_file}")
    
    # Check what content was included
    has_blurbs = any(f"MATCHUP{i}_BLURB" in ctx for i in range(1, 8))
    has_spotlights = any(f"MATCHUP{i}_TOP_HOME" in ctx for i in range(1, 8))
    has_logos = any("_LOGO" in key for key in ctx)
    has_awards = "AWARD_CUPCAKE_TEAM" in ctx
    
    logger.info("\nContent included:")
    logger.info(f"  ✅ Matchup scores: Yes")
    logger.info(f"  {'✅' if has_blurbs else '❌'} Sabre blurbs: {'Yes' if has_blurbs else 'No'}")
    logger.info(f"  {'✅' if has_spotlights else '❌'} Stats spotlights: {'Yes' if has_spotlights else 'No'}")
    logger.info(f"  {'✅' if has_logos else '❌'} Team logos: {'Yes' if has_logos else 'No'}")
    logger.info(f"  {'✅' if has_awards else '❌'} Weekly awards: {'Yes' if has_awards else 'No'}")
    
    if ctx.get("LEAGUE_LOGO"):
        logger.info(f"  ✅ League logo: {ctx['LEAGUE_LOGO']}")
    else:
        logger.info(f"  ❌ League logo: Not found")
    
    # Check for markdown artifacts (should be none)
    markdown_found = False
    for key, value in ctx.items():
        if isinstance(value, str) and any(marker in str(value) for marker in ['**', '__', '##', '`']):
            logger.warning(f"  ⚠️  Markdown found in {key}: {value[:50]}...")
            markdown_found = True
    
    if not markdown_found:
        logger.info("  ✅ All markdown cleaned: Yes")
    
    logger.info("="*60 + "\n")


def _safe(s: Any) -> str:
    """Safely convert any value to string."""
    return "" if s is None else str(s)


# ==================
# Testing utilities
# ==================

def test_recap_generation():
    """Test the recap generation with sample data."""
    print("Testing Weekly Recap Generation")
    print("=" * 50)
    
    # Create sample context
    sample_ctx = {
        "WEEK_NUMBER": 3,
        "WEEK": 3,
        "YEAR": 2025,
        "LEAGUE_NAME": "Browns Fantasy League",
        "MATCHUP_COUNT": 2,
        
        # Sample matchup 1
        "MATCHUP1_HOME": "Thunder Hawks",
        "MATCHUP1_AWAY": "Lightning Bolts",
        "MATCHUP1_HS": "125.50",
        "MATCHUP1_AS": "98.75",
        "MATCHUP1_HOME_TOP_SCORER": "Josh Allen",
        "MATCHUP1_HOME_TOP_POINTS": "32.5",
        "MATCHUP1_AWAY_TOP_SCORER": "Justin Jefferson",
        "MATCHUP1_AWAY_TOP_POINTS": "28.2",
        
        # Sample matchup 2  
        "MATCHUP2_HOME": "Fire Dragons",
        "MATCHUP2_AWAY": "Ice Warriors",
        "MATCHUP2_HS": "115.25",
        "MATCHUP2_AS": "114.50",
        
        # Awards
        "AWARD_CUPCAKE_TEAM": "Team Disaster",
        "AWARD_CUPCAKE_NOTE": "65.3",
        "AWARD_KITTY_TEAM": "Almost Winners",
        "AWARD_KITTY_NOTE": "fell to Thunder Hawks by 0.5",
        "AWARD_TOP_TEAM": "Thunder Hawks",
        "AWARD_TOP_NOTE": "125.50"
    }
    
    print("Sample context created with:")
    print(f"  - {sample_ctx['MATCHUP_COUNT']} matchups")
    print(f"  - Week {sample_ctx['WEEK_NUMBER']}, Year {sample_ctx['YEAR']}")
    print(f"  - League: {sample_ctx['LEAGUE_NAME']}")
    
    # Test Sabre blurb generation
    print("\nTesting Sabre blurb generation...")
    _attach_sabre_recaps(sample_ctx)
    
    if "MATCHUP1_BLURB" in sample_ctx:
        print("✅ Sabre blurb generated")
        print(f"   Length: {len(sample_ctx['MATCHUP1_BLURB'])} chars")
        
        # Check for markdown
        if "**" in sample_ctx["MATCHUP1_BLURB"]:
            print("❌ Markdown found in blurb (should be cleaned)")
        else:
            print("✅ No markdown in blurb")
    else:
        print("❌ No Sabre blurb generated")
    
    # Test spotlight content
    print("\nTesting spotlight content generation...")
    _attach_spotlight_content(sample_ctx)
    
    spotlight_fields = ["MATCHUP1_TOP_HOME", "MATCHUP1_TOP_AWAY", "MATCHUP1_BUST", "MATCHUP1_KEYPLAY", "MATCHUP1_DEF"]
    for field in spotlight_fields:
        if field in sample_ctx:
            print(f"✅ {field}: {sample_ctx[field][:50]}...")
        else:
            print(f"❌ {field}: Missing")
    
    # Test markdown cleaning
    print("\nTesting markdown cleaning...")
    test_text = "This has **bold** and *italic* text"
    cleaned = clean_markdown_for_docx(test_text)
    if cleaned == "This has bold and italic text":
        print("✅ Markdown cleaning works")
    else:
        print(f"❌ Markdown cleaning failed: {cleaned}")
    
    print("\n" + "=" * 50)
    print("Test complete!")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_recap_generation()
    else:
        print("Weekly Recap Builder")
        print("This module is typically called from build_gazette.py")
        print("\nTo test: python weekly_recap.py test")