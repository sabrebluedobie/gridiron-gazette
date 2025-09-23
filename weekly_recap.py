from __future__ import annotations
import logging
from pathlib import Path
from typing import Any, Dict

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

from gazette_data import build_context
import logo_resolver as logos

log = logging.getLogger("weekly_recap")

# --- Optional Sabre blurbs (storymaker) ---
try:
    from storymaker import generate_spotlights_for_week
    log.info("Storymaker imported successfully")
except Exception as e:
    log.warning(f"Failed to import storymaker: {e}")
    def generate_spotlights_for_week(ctx: Dict[str, Any], style: str, words: int) -> Dict[str, Dict[str, str]]:
        # Fallback: produce simple stat-based spotlights so the section is never blank
        log.info("Using fallback spotlight generator")
        out: Dict[str, Dict[str, str]] = {}
        for i in range(1, 8):
            h = ctx.get(f"MATCHUP{i}_HOME")
            a = ctx.get(f"MATCHUP{i}_AWAY")
            if not (h and a):
                continue
            hs = ctx.get(f"MATCHUP{i}_HS", "")
            as_ = ctx.get(f"MATCHUP{i}_AS", "")
            hts = ctx.get(f"MATCHUP{i}_HOME_TOP_SCORER", "")
            htp = ctx.get(f"MATCHUP{i}_HOME_TOP_POINTS", "")
            ats = ctx.get(f"MATCHUP{i}_AWAY_TOP_SCORER", "")
            atp = ctx.get(f"MATCHUP{i}_AWAY_TOP_POINTS", "")
            
            out[str(i)] = {
                "home": f"Top Scorer (Home): {hts} {f'({htp})' if htp else ''}".strip() if hts else "Top Scorer (Home): —",
                "away": f"Top Scorer (Away): {ats} {f'({atp})' if atp else ''}".strip() if ats else "Top Scorer (Away): —",
                "bust": "Biggest Bust: Performance below expectations",
                "key": f"Key Play: {h} {hs} vs {a} {as_}" if h and a else "Key Play: —",
                "def": "Defense Note: Solid defensive showing",
            }
        return out


def _inject_exact_template_variables(ctx: Dict[str, Any], style: str, words: int) -> None:
    """
    Generate and inject the EXACT variable names the template expects.
    Based on template inspector output:
    
    SPOTLIGHT VARIABLES:
    - MATCHUP1_TOP_HOME, MATCHUP1_TOP_AWAY
    - MATCHUP1_BUST, MATCHUP1_DEF, MATCHUP1_KEYPLAY
    - MATCHUP2_BUST, MATCHUP2_DEF, MATCHUP2_KEYPLAY, etc.
    
    MATCHUP VARIABLES:
    - MATCHUP1_HS, MATCHUP1_AS (scores)
    - MATCHUP1_HOME, MATCHUP1_AWAY (team names)
    """
    log.info(f"Generating EXACT template variables - style: {style}, words: {words}")
    
    try:
        blocks = generate_spotlights_for_week(ctx, style=style, words=words)
        log.info(f"Generated spotlights for {len(blocks)} matchups")
    except Exception as e:
        log.error(f"Failed to generate spotlights: {e}")
        blocks = {}
    
    # Generate the EXACT variable patterns the template expects
    for i in range(1, 8):
        # Get existing matchup data
        home_name = ctx.get(f"MATCHUP{i}_HOME", "")
        away_name = ctx.get(f"MATCHUP{i}_AWAY", "")
        home_score = ctx.get(f"MATCHUP{i}_HS", "")
        away_score = ctx.get(f"MATCHUP{i}_AS", "")
        home_top_scorer = ctx.get(f"MATCHUP{i}_HOME_TOP_SCORER", "")
        home_top_points = ctx.get(f"MATCHUP{i}_HOME_TOP_POINTS", "")
        away_top_scorer = ctx.get(f"MATCHUP{i}_AWAY_TOP_SCORER", "")
        away_top_points = ctx.get(f"MATCHUP{i}_AWAY_TOP_POINTS", "")
        
        if not (home_name and away_name):
            continue
            
        # Get spotlight content for this matchup
        block = blocks.get(str(i), {})
        
        # EXACT TEMPLATE VARIABLE NAMES from template inspector:
        
        # Top scorers - template expects MATCHUP1_TOP_HOME format
        home_top_display = f"{home_top_scorer} ({home_top_points})" if home_top_scorer and home_top_points else ""
        away_top_display = f"{away_top_scorer} ({away_top_points})" if away_top_scorer and away_top_points else ""
        
        ctx[f"MATCHUP{i}_TOP_HOME"] = home_top_display
        ctx[f"MATCHUP{i}_TOP_AWAY"] = away_top_display
        
        # Spotlight content - template expects MATCHUP1_BUST, MATCHUP1_DEF, MATCHUP1_KEYPLAY
        ctx[f"MATCHUP{i}_BUST"] = block.get("bust", "")
        ctx[f"MATCHUP{i}_DEF"] = block.get("def", "")
        ctx[f"MATCHUP{i}_KEYPLAY"] = block.get("key", "")
        
        # Log what we're setting for debugging
        log.info(f"Setting MATCHUP{i} template variables:")
        log.info(f"  MATCHUP{i}_TOP_HOME = '{home_top_display}'")
        log.info(f"  MATCHUP{i}_TOP_AWAY = '{away_top_display}'")
        log.info(f"  MATCHUP{i}_BUST = '{block.get('bust', '')[:50]}...'")
        log.info(f"  MATCHUP{i}_DEF = '{block.get('def', '')[:50]}...'")
        log.info(f"  MATCHUP{i}_KEYPLAY = '{block.get('key', '')[:50]}...'")

    # Count variables for verification
    template_vars = len([k for k in ctx.keys() if any(x in k for x in ["_TOP_", "_BUST", "_DEF", "_KEYPLAY"])])
    log.info(f"Set {template_vars} template-specific variables")


def _make_basic_aliases(ctx: Dict[str, Any]) -> None:
    """Create only essential aliases"""
    week = ctx.get("WEEK_NUMBER")
    league = ctx.get("LEAGUE_NAME") or "League"
    
    # Basic template requirements
    ctx.setdefault("title", f"Week {week} Fantasy Football Gazette")
    ctx.setdefault("TITLE", f"Week {week} Fantasy Football Gazette — {league}")
    ctx.setdefault("SUBTITLE", "For those times when everyone wants to know your score.")


def _handle_awards_manually(ctx: Dict[str, Any]) -> None:
    """
    Since template has NO award variables, we need to manually insert award text
    into the document or create fallback content. The template shows static text
    with placeholder "---" values.
    """
    # The template doesn't have award variables, but we can log what we have
    cupcake = ctx.get("CUPCAKE_LINE", "—")
    kitty = ctx.get("KITTY_LINE", "—") 
    topscore = ctx.get("TOPSCORE_LINE", "—")
    
    log.info(f"Awards computed but template has no award variables:")
    log.info(f"  Cupcake: {cupcake}")
    log.info(f"  Kitty: {kitty}")
    log.info(f"  Top Score: {topscore}")
    
    # Note: Template will continue to show "---" until template is updated
    # with proper award variables like {{ CUPCAKE_AWARD }}, etc.


def _attach_images(ctx: Dict[str, Any], doc: DocxTemplate) -> None:
    """Attach logos - template expects LEAGUE_LOGO"""
    league_name = str(ctx.get("LEAGUE_NAME") or "")
    sponsor_name = str(ctx.get("SPONSOR_NAME") or "Gridiron Gazette")

    # League logo - template expects LEAGUE_LOGO
    try:
        lg_raw = logos.league_logo(league_name)
        if lg_raw:
            lg = logos.sanitize_logo_for_docx(lg_raw)
            if lg and Path(lg).exists():
                ctx["LEAGUE_LOGO"] = InlineImage(doc, lg, width=Mm(25))
                log.info(f"League logo attached: LEAGUE_LOGO")
            else:
                log.warning(f"League logo sanitization failed: {lg_raw}")
        else:
            log.warning(f"No league logo found for: {league_name}")
    except Exception as e:
        log.error(f"Error attaching league logo: {e}")

    # Sponsor logo
    try:
        sp_raw = logos.sponsor_logo(sponsor_name)
        if sp_raw:
            sp = logos.sanitize_logo_for_docx(sp_raw)
            if sp and Path(sp).exists():
                ctx["SPONSOR_LOGO"] = InlineImage(doc, sp, width=Mm(25))
                log.info(f"Sponsor logo attached: SPONSOR_LOGO")
            else:
                log.warning(f"Sponsor logo sanitization failed: {sp_raw}")
        else:
            log.warning(f"No sponsor logo found for: {sponsor_name}")
    except Exception as e:
        log.error(f"Error attaching sponsor logo: {e}")

    # Team logos - based on template pattern
    for i in range(1, 8):
        home_key = f"MATCHUP{i}_HOME"
        away_key = f"MATCHUP{i}_AWAY"
        
        # Home team logo
        if home_key in ctx and ctx[home_key]:
            try:
                home_name = str(ctx[home_key])
                hp_raw = logos.team_logo(home_name)
                if hp_raw:
                    hp = logos.sanitize_logo_for_docx(hp_raw)
                    if hp and Path(hp).exists():
                        ctx[f"MATCHUP{i}_HOME_LOGO"] = InlineImage(doc, hp, width=Mm(22))
                        log.debug(f"Home logo attached: MATCHUP{i}_HOME_LOGO")
                    else:
                        log.warning(f"Home logo sanitization failed for {home_name}")
                else:
                    log.warning(f"No home logo found for: {home_name}")
            except Exception as e:
                log.error(f"Error attaching home logo {i}: {e}")

        # Away team logo  
        if away_key in ctx and ctx[away_key]:
            try:
                away_name = str(ctx[away_key])
                ap_raw = logos.team_logo(away_name)
                if ap_raw:
                    ap = logos.sanitize_logo_for_docx(ap_raw)
                    if ap and Path(ap).exists():
                        ctx[f"MATCHUP{i}_AWAY_LOGO"] = InlineImage(doc, ap, width=Mm(22))
                        log.debug(f"Away logo attached: MATCHUP{i}_AWAY_LOGO")
                    else:
                        log.warning(f"Away logo sanitization failed for {away_name}")
                else:
                    log.warning(f"No away logo found for: {away_name}")
            except Exception as e:
                log.error(f"Error attaching away logo {i}: {e}")


def render_docx(template_path: str, outdocx: str, context: Dict[str, Any]) -> str:
    """Render DOCX with exact template variable matching"""
    log.info(f"Rendering DOCX from template: {template_path}")
    log.info(f"Output path: {outdocx}")
    
    if not Path(template_path).exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    
    try:
        doc = DocxTemplate(template_path)
        log.info("Template loaded successfully")
        
        # Process context with EXACT template variable names
        log.info("Creating basic aliases...")
        _make_basic_aliases(context)
        
        log.info("Injecting EXACT template variables...")
        _inject_exact_template_variables(
            context, 
            style=context.get("BLURB_STYLE", "sabre"), 
            words=int(context.get("BLURB_WORDS", 200))
        )
        
        log.info("Handling awards (template has no award variables)...")
        _handle_awards_manually(context)
        
        log.info("Attaching images...")
        _attach_images(context, doc)
        
        # Log final variable summary
        total_vars = len(context)
        template_vars = len([k for k in context.keys() if any(x in k for x in ["_TOP_", "_BUST", "_DEF", "_KEYPLAY"])])
        
        log.info(f"Final context: {total_vars} total vars, {template_vars} template-specific vars")
        
        # Show a few key variables for verification
        log.info("Key template variables:")
        for i in range(1, min(3, 6)):  # Show first 2 matchups
            if f"MATCHUP{i}_HOME" in context:
                log.info(f"  MATCHUP{i}_TOP_HOME = '{context.get(f'MATCHUP{i}_TOP_HOME', 'NOT SET')}'")
                log.info(f"  MATCHUP{i}_BUST = '{context.get(f'MATCHUP{i}_BUST', 'NOT SET')[:30]}...'")
        
        # Ensure output directory exists
        Path(outdocx).parent.mkdir(parents=True, exist_ok=True)
        
        log.info("Rendering document...")
        doc.render(context)
        
        log.info("Saving document...")
        doc.save(outdocx)
        
        log.info(f"Document rendered successfully: {outdocx}")
        return outdocx
        
    except Exception as e:
        log.error(f"Failed to render DOCX: {e}")
        raise


def build_weekly_recap(
    league: Any,
    league_id: int,
    year: int,
    week: int,
    template: str,
    output_dir: str,
    llm_blurbs: bool = True,
    blurb_style: str = "sabre",
    blurb_words: int = 200,
) -> str:
    """Build weekly recap with exact template variable matching"""
    log.info(f"Building weekly recap - League: {league_id}, Year: {year}, Week: {week}")
    log.info(f"Template: {template}")
    log.info(f"LLM Blurbs: {llm_blurbs}, Style: {blurb_style}, Words: {blurb_words}")
    
    try:
        # Build context from ESPN data
        ctx = build_context(league_id=league_id, year=year, week=week)
        
        # Add blurb configuration
        ctx.setdefault("BLURB_STYLE", blurb_style or "sabre")
        ctx.setdefault("BLURB_WORDS", blurb_words or 200)
        ctx.setdefault("LLM_BLURBS", llm_blurbs)

        # Process output path with token replacement
        week_num = int(ctx.get("WEEK_NUMBER", week or 0) or 0)
        league_name = ctx.get("LEAGUE_NAME", "League")
        
        out_path = output_dir
        out_path = out_path.replace("{year}", str(ctx.get("YEAR", year)))
        out_path = out_path.replace("{league}", str(league_name))
        out_path = out_path.replace("{week}", str(week_num))
        out_path = out_path.replace("{week02}", f"{week_num:02d}")
        
        # Ensure .docx extension
        if not out_path.lower().endswith(".docx"):
            out_path = str(Path(out_path) / f"gazette_week_{week_num}.docx")

        log.info(f"Final output path: {out_path}")
        
        # Log context summary
        log.info(f"Context summary:")
        log.info(f"  League: {ctx.get('LEAGUE_NAME')}")
        log.info(f"  Week: {ctx.get('WEEK_NUMBER')}")
        log.info(f"  Matchups: {ctx.get('MATCHUP_COUNT', 0)}")
        log.info(f"  Awards: Cupcake={bool(ctx.get('AWARD_CUPCAKE_TEAM'))}, "
                f"Kitty={bool(ctx.get('AWARD_KITTY_WINNER'))}, "
                f"TopScore={bool(ctx.get('AWARD_TOPSCORE_TEAM'))}")
        
        # Render the document
        result = render_docx(template, out_path, ctx)
        log.info(f"Weekly recap completed successfully: {result}")
        return result
        
    except Exception as e:
        log.error(f"Failed to build weekly recap: {e}")
        raise