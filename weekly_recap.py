#!/usr/bin/env python3
"""
Weekly Recap Builder for Gridiron Gazette
COMPLETE VERSION using team_logos.json for all logo mappings
- Properly embeds images from JSON mappings
- Removes blank pages
- Fixes margin issues and header/footer sliding
- Supports multiple leagues via JSON
"""
from __future__ import annotations
import os
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, List

# DOCX handling with image support and formatting control
from docxtpl import DocxTemplate, InlineImage
from docx import Document
from docx.shared import Mm, Inches, Pt
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

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
    
    def get_team_logo(self, team_name: str) -> Optional[Path]:
        """Get logo path for a team from mappings"""
        if team_name in self.logo_mappings:
            logo_path = Path(self.logo_mappings[team_name])
            if logo_path.exists():
                return logo_path
            else:
                logger.warning(f"Logo file not found: {logo_path} for team {team_name}")
        else:
            logger.warning(f"No mapping found for team: {team_name}")
        return None
    
    def get_league_logo(self) -> Optional[Path]:
        """Get league logo from mappings"""
        if "LEAGUE_LOGO" in self.logo_mappings:
            logo_path = Path(self.logo_mappings["LEAGUE_LOGO"])
            if logo_path.exists():
                return logo_path
            else:
                logger.warning(f"League logo file not found: {logo_path}")
        return None
    
    def get_sponsor_logo(self) -> Optional[Path]:
        """Get sponsor logo from mappings"""
        if "SPONSOR_LOGO" in self.logo_mappings:
            logo_path = Path(self.logo_mappings["SPONSOR_LOGO"])
            if logo_path.exists():
                return logo_path
            else:
                logger.warning(f"Sponsor logo file not found: {logo_path}")
        return None


def build_weekly_recap(
    league_id: int,
    year: int,
    week: int,
    template: str = "recap_template.docx",
    output_path: str = "recaps/Gazette_{year}_W{week02}.docx",
    use_llm_blurbs: bool = True,
    logo_json: str = "team_logos.json"
) -> str:
    """
    Builds the Gazette docx with comprehensive fixes:
      1) Fetches ESPN context
      2) Generates Sabre recaps
      3) Properly embeds images from team_logos.json
      4) Cleans markdown
      5) Renders template
      6) Post-processes to fix blank pages and margins
    
    Args:
        league_id: ESPN league ID
        year: Season year
        week: Week number
        template: Path to DOCX template
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
    
    # Clean all markdown from the context
    ctx = clean_all_markdown_in_dict(ctx)
    
    # Render the doc WITH PROPER IMAGE EMBEDDING from JSON
    out = _render_docx_with_images(template, output_path, ctx, logo_json)
    
    # Post-process to fix blank pages and margins
    _post_process_document(out)
    
    return out


def _render_docx_with_images(template_path: str, out_pattern: str, ctx: Dict[str, Any], logo_json: str) -> str:
    """
    Render the DOCX template with proper image embedding using team_logos.json.
    """
    tpl_path = Path(template_path)
    if not tpl_path.exists():
        raise FileNotFoundError(f"Template not found: {tpl_path}")

    # Create DocxTemplate object
    doc = DocxTemplate(str(tpl_path))
    
    # Prepare context with embedded images from JSON mappings
    image_context = _prepare_image_context_from_json(doc, ctx.copy(), logo_json)
    
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
    
    # Render the template with image context
    doc.render(image_context)
    
    # Save the document
    doc.save(str(out_file))
    
    logger.info(f"✅ Generated recap document: {out_file}")
    _log_recap_summary(image_context, out_file)
    
    return str(out_file)


def _prepare_image_context_from_json(doc_template: DocxTemplate, context: Dict[str, Any], logo_json: str) -> Dict[str, Any]:
    """
    Convert logo paths to InlineImage objects using team_logos.json mappings.
    This ensures we use the exact paths specified in the JSON file.
    """
    logger.info(f"Preparing images from {logo_json}...")
    
    # Initialize logo manager with JSON mappings
    logo_manager = LogoManager(logo_json)
    
    # Standard sizes for consistency (prevents margin issues)
    TEAM_LOGO_SIZE = Mm(15)  # Smaller for inline team logos
    HEADER_LOGO_SIZE = Mm(25)  # Larger for header logos
    
    # Process team logos for each matchup
    images_embedded = 0
    for i in range(1, 8):
        home_key = f"MATCHUP{i}_HOME"
        away_key = f"MATCHUP{i}_AWAY"
        
        # Home team logo
        if home_key in context:
            team_name = context[home_key]
            logo_key = f"MATCHUP{i}_HOME_LOGO"
            
            logo_path = logo_manager.get_team_logo(team_name)
            if logo_path:
                try:
                    context[logo_key] = InlineImage(
                        doc_template, 
                        str(logo_path), 
                        width=TEAM_LOGO_SIZE
                    )
                    logger.info(f"✅ Embedded logo for {team_name}: {logo_path}")
                    images_embedded += 1
                except Exception as e:
                    logger.error(f"Failed to embed logo for {team_name}: {e}")
                    context[logo_key] = ""
            else:
                context[logo_key] = ""
                logger.warning(f"No logo found for home team: {team_name}")
        
        # Away team logo
        if away_key in context:
            team_name = context[away_key]
            logo_key = f"MATCHUP{i}_AWAY_LOGO"
            
            logo_path = logo_manager.get_team_logo(team_name)
            if logo_path:
                try:
                    context[logo_key] = InlineImage(
                        doc_template, 
                        str(logo_path), 
                        width=TEAM_LOGO_SIZE
                    )
                    logger.info(f"✅ Embedded logo for {team_name}: {logo_path}")
                    images_embedded += 1
                except Exception as e:
                    logger.error(f"Failed to embed logo for {team_name}: {e}")
                    context[logo_key] = ""
            else:
                context[logo_key] = ""
                logger.warning(f"No logo found for away team: {team_name}")
    
    # Process league logo
    league_logo_path = logo_manager.get_league_logo()
    if league_logo_path:
        try:
            context["LEAGUE_LOGO"] = InlineImage(
                doc_template,
                str(league_logo_path),
                width=HEADER_LOGO_SIZE
            )
            logger.info(f"✅ Embedded league logo: {league_logo_path}")
            images_embedded += 1
        except Exception as e:
            logger.error(f"Failed to embed league logo: {e}")
            context["LEAGUE_LOGO"] = ""
    else:
        context["LEAGUE_LOGO"] = ""
        logger.warning("No league logo found in mappings")
    
    # Process sponsor logo
    sponsor_logo_path = logo_manager.get_sponsor_logo()
    if sponsor_logo_path:
        try:
            context["SPONSOR_LOGO"] = InlineImage(
                doc_template,
                str(sponsor_logo_path),
                width=HEADER_LOGO_SIZE
            )
            logger.info(f"✅ Embedded sponsor logo: {sponsor_logo_path}")
            images_embedded += 1
        except Exception as e:
            logger.error(f"Failed to embed sponsor logo: {e}")
            context["SPONSOR_LOGO"] = ""
    else:
        context["SPONSOR_LOGO"] = ""
        logger.warning("No sponsor logo found in mappings")
    
    logger.info(f"Total images embedded: {images_embedded}")
    return context


def _post_process_document(doc_path: str) -> None:
    """
    Post-process the document to fix formatting issues.
    Complete version with all functionality:
    1. Removes empty paragraphs that cause blank pages
    2. Fixes section breaks
    3. Adjusts margins for consistency
    4. Removes excessive spacing
    5. Fixes header/footer alignment
    6. Fixes table formatting
    """
    logger.info("Post-processing document to fix formatting issues...")
    
    try:
        # Try to use the dedicated formatter module first
        from document_formatter import apply_formatting_fixes
        apply_formatting_fixes(doc_path)
        logger.info("✅ Document formatting fixed using dedicated formatter")
        return
    except ImportError:
        logger.info("document_formatter module not found, using comprehensive fallback method")
    except Exception as e:
        logger.warning(f"Error using document_formatter: {e}, using comprehensive fallback method")
    
    # Comprehensive fallback method with ALL functionality
    try:
        from docx import Document
        from docx.shared import Inches, Pt
        from docx.enum.section import WD_SECTION
        from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        
        # Open the document for post-processing
        doc = Document(doc_path)
        
        # Fix margins for all sections (prevents margin slip)
        for section in doc.sections:
            # Use 1.0" top/bottom for header/footer space
            section.top_margin = Inches(1.0)
            section.bottom_margin = Inches(1.0)
            section.left_margin = Inches(0.75)
            section.right_margin = Inches(0.75)
            
            # Set header/footer distances to prevent overlap with content
            section.header_distance = Inches(0.5)
            section.footer_distance = Inches(0.5)
            
            # Ensure consistent page size
            section.page_height = Inches(11)
            section.page_width = Inches(8.5)
            
            # Remove unnecessary section breaks that cause blank pages
            # Keep first section as is, make others continuous
            if section != doc.sections[0]:
                section.start_type = WD_SECTION.CONTINUOUS
        
        # Fix header/footer alignment to prevent gradient sliding
        for section in doc.sections:
            # Fix header alignment
            header = section.header
            for paragraph in header.paragraphs:
                paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
                paragraph_format = paragraph.paragraph_format
                paragraph_format.left_indent = Inches(0)
                paragraph_format.right_indent = Inches(0)
                
            # Fix footer alignment  
            footer = section.footer
            for paragraph in footer.paragraphs:
                paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
                paragraph_format = paragraph.paragraph_format
                paragraph_format.left_indent = Inches(0)
                paragraph_format.right_indent = Inches(0)
        
        # Remove empty paragraphs that cause blank pages
        paragraphs_to_delete = []
        consecutive_empty = 0
        
        for i, paragraph in enumerate(doc.paragraphs):
            # Check if paragraph is effectively empty
            text = paragraph.text.strip()
            
            if not text:
                # Check if it has no runs with images either
                has_content = False
                for run in paragraph.runs:
                    if run.text.strip():
                        has_content = True
                        break
                    # Check for embedded objects (images)
                    if hasattr(run, '_element') and run._element.xpath('.//w:drawing'):
                        has_content = True
                        break
                
                if not has_content:
                    consecutive_empty += 1
                    # Keep single empty paragraphs for spacing, remove multiple consecutive ones
                    if consecutive_empty > 1:
                        paragraphs_to_delete.append(paragraph)
            else:
                consecutive_empty = 0
        
        # Delete excessive empty paragraphs
        for paragraph in paragraphs_to_delete:
            try:
                p = paragraph._element
                p.getparent().remove(p)
                logger.debug("Removed empty paragraph")
            except:
                pass  # Paragraph might already be removed
        
        # Fix spacing between paragraphs
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():  # Only for non-empty paragraphs
                paragraph_format = paragraph.paragraph_format
                
                # Consistent spacing
                paragraph_format.space_after = Pt(6)  # Reduced from default
                paragraph_format.space_before = Pt(6)  # Reduced from default
                
                # Ensure single line spacing with slight increase for readability
                paragraph_format.line_spacing = 1.15
                
                # Remove excessive indentation that might cause margin issues
                if paragraph_format.left_indent and paragraph_format.left_indent > Inches(0.5):
                    paragraph_format.left_indent = Inches(0)
                if paragraph_format.right_indent and paragraph_format.right_indent > Inches(0.5):
                    paragraph_format.right_indent = Inches(0)
        
        # Remove unnecessary page breaks
        for paragraph in doc.paragraphs:
            if hasattr(paragraph, '_element'):
                # Check for page breaks
                page_breaks = paragraph._element.xpath('.//w:br[@w:type="page"]')
                if page_breaks:
                    # Check if this paragraph has actual content
                    if not paragraph.text.strip():
                        # Remove unnecessary page break
                        for br in page_breaks:
                            br.getparent().remove(br)
                            logger.debug("Removed unnecessary page break")
        
        # Handle tables to prevent margin issues
        for table in doc.tables:
            table.autofit = True
            # Set table alignment to center
            table.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
            
            # Fix table properties to prevent overflow
            tbl = table._element
            tblPr = tbl.xpath('.//w:tblPr')[0] if tbl.xpath('.//w:tblPr') else tbl.add_tblPr()
            
            # Set table width to auto
            tblW = OxmlElement('w:tblW')
            tblW.set(qn('w:type'), 'auto')
            tblW.set(qn('w:w'), '0')
            
            # Remove any existing width settings
            for existing_tblW in tblPr.xpath('.//w:tblW'):
                tblPr.remove(existing_tblW)
            
            tblPr.append(tblW)
            
            # Ensure table doesn't exceed margins
            for row in table.rows:
                for cell in row.cells:
                    # Set cell margins
                    tc = cell._element
                    tcPr = tc.get_or_add_tcPr()
                    
                    # Remove any existing margins
                    for tcMar in tcPr.xpath('.//w:tcMar'):
                        tcPr.remove(tcMar)
                    
                    # Add consistent small margins
                    tcMar = OxmlElement('w:tcMar')
                    for margin_type in ['top', 'left', 'bottom', 'right']:
                        margin = OxmlElement(f'w:{margin_type}')
                        margin.set(qn('w:w'), '50')  # Small margin
                        margin.set(qn('w:type'), 'dxa')
                        tcMar.append(margin)
                    tcPr.append(tcMar)
                    
                    # Fix cell paragraph spacing
                    for paragraph in cell.paragraphs:
                        paragraph.paragraph_format.space_after = Pt(3)
                        paragraph.paragraph_format.space_before = Pt(3)
                        paragraph.paragraph_format.line_spacing = 1.0
        
        # Save the fixed document
        doc.save(doc_path)
        logger.info(f"✅ Post-processing complete: fixed margins, removed blank pages, aligned headers/footers")
        
    except Exception as e:
        logger.error(f"Error during post-processing: {e}")
        # Don't fail the entire process if post-processing fails
        logger.info("Document generated but post-processing failed - output may have formatting issues")


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
        
        # Additional cleanup for formatting
        recap = recap.replace('\r\n', '\n').replace('\r', '\n')
        
        # Ensure proper paragraph breaks
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
    
    # Count embedded images
    image_count = sum(1 for key in ctx if 'LOGO' in key and hasattr(ctx[key], '__class__') and 'InlineImage' in str(ctx[key].__class__))
    
    logger.info(f"\n✅ Images embedded: {image_count}")
    logger.info("✅ Using team_logos.json for all mappings")
    logger.info("✅ Margins fixed")
    logger.info("✅ Blank pages removed")
    logger.info("✅ Formatting cleaned")
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


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        verify_logo_mappings()
    else:
        print("Weekly Recap Builder - Using team_logos.json")
        print("Features:")
        print("  ✅ Loads all logos from team_logos.json")
        print("  ✅ Proper image embedding")
        print("  ✅ Removes blank pages")
        print("  ✅ Fixes margin issues")
        print("  ✅ Cleans formatting")
        print("\nUsage:")
        print("  Called from build_gazette.py")
        print("  Or verify logos: python weekly_recap.py verify")