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


def _generate_sabre_blurbs(ctx: Dict[str, Any], style: str, words: int) -> Dict[str, str]:
    """Generate Sabre's news article blurbs for each matchup"""
    log.info(f"Generating Sabre blurbs - style: {style}, words: {words}")
    
    try:
        from storymaker import generate_spotlights_for_week
        
        # Generate spotlight content first
        spotlights = generate_spotlights_for_week(ctx, style=style, words=words)
        
        # Convert spotlights into full Sabre blurbs (news articles)
        blurbs = {}
        
        for i in range(1, 8):
            home_name = ctx.get(f"MATCHUP{i}_HOME", "")
            away_name = ctx.get(f"MATCHUP{i}_AWAY", "")
            home_score = ctx.get(f"MATCHUP{i}_HS", "")
            away_score = ctx.get(f"MATCHUP{i}_AS", "")
            
            if not (home_name and away_name):
                continue
                
            # Get spotlight details
            spotlight = spotlights.get(str(i), {})
            
            # Create a full Sabre news blurb
            winner = home_name if float(home_score or 0) >= float(away_score or 0) else away_name
            loser = away_name if float(home_score or 0) >= float(away_score or 0) else home_name
            margin = abs(float(home_score or 0) - float(away_score or 0))
            
            blurb = f"""
{winner} edged out {loser} {home_score}-{away_score} in what can only be described as {'a nail-biter' if margin < 5 else 'a decisive victory' if margin > 20 else 'a solid win'}.

{spotlight.get('home', 'The home team put up a fight.')} Meanwhile, {spotlight.get('away', 'the away team showed resilience.')  }

{spotlight.get('bust', 'Some players had better days than others.')} {spotlight.get('key', 'The game had its moments.')}

{spotlight.get('def', 'Defense played its part in the outcome.')}

— Sabre, Gridiron Gazette
            """.strip()
            
            blurbs[str(i)] = blurb
            
        log.info(f"Generated {len(blurbs)} Sabre blurbs")
        return blurbs
        
    except Exception as e:
        log.error(f"Failed to generate Sabre blurbs: {e}")
        return {}


def _inject_exact_template_variables(ctx: Dict[str, Any], style: str, words: int) -> None:
    """Generate exact template variables + add blurb variables"""
    log.info(f"Generating EXACT template variables + blurbs - style: {style}, words: {words}")
    
    try:
        blocks = generate_spotlights_for_week(ctx, style=style, words=words)
        log.info(f"Generated spotlights for {len(blocks)} matchups")
    except Exception as e:
        log.error(f"Failed to generate spotlights: {e}")
        blocks = {}
    
    # Generate Sabre blurbs (news articles)
    sabre_blurbs = _generate_sabre_blurbs(ctx, style, words)
    
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
        
        # ADD ALL POSSIBLE BLURB VARIABLE PATTERNS
        sabre_blurb = sabre_blurbs.get(str(i), "")
        if sabre_blurb:
            # Multiple possible blurb variable patterns
            blurb_patterns = [
                f"MATCHUP{i}_BLURB",
                f"MATCHUP{i}.blurb", 
                f"matchup{i}.blurb",
                f"BLURB{i}",
                f"SABRE_BLURB_{i}",
                f"ARTICLE{i}",
                f"STORY{i}",
                f"NEWS{i}",
            ]
            
            for pattern in blurb_patterns:
                ctx[pattern] = sabre_blurb
        
        # Log what we're setting for debugging
        if i <= 2:  # Log first 2 for brevity
            log.info(f"Setting MATCHUP{i} variables:")
            log.info(f"  MATCHUP{i}_TOP_HOME = '{home_top_display}'")
            log.info(f"  MATCHUP{i}_TOP_AWAY = '{away_top_display}'")
            log.info(f"  MATCHUP{i}_BUST = '{block.get('bust', '')[:30]}...'")
            if sabre_blurb:
                log.info(f"  MATCHUP{i}_BLURB = '{sabre_blurb[:50]}...'")

    # Count variables for verification
    template_vars = len([k for k in ctx.keys() if any(x in k for x in ["_TOP_", "_BUST", "_DEF", "_KEYPLAY", "_BLURB"])])
    log.info(f"Set {template_vars} template-specific variables")


def _make_basic_aliases(ctx: Dict[str, Any]) -> None:
    """Create essential aliases"""
    week = ctx.get("WEEK_NUMBER")
    league = ctx.get("LEAGUE_NAME") or "League"
    
    # Basic template requirements
    ctx.setdefault("title", f"Week {week} Fantasy Football Gazette")
    ctx.setdefault("TITLE", f"Week {week} Fantasy Football Gazette — {league}")
    ctx.setdefault("SUBTITLE", "For those times when everyone wants to know your score.")


def _fix_league_logo_resolution(ctx: Dict[str, Any]) -> None:
    """Fix league logo resolution - ensure brownseakc.png is found"""
    league_name = ctx.get("LEAGUE_NAME", "")
    
    log.info(f"Fixing league logo resolution for: '{league_name}'")
    
    # Direct path check for the logo you mentioned
    direct_logo_path = Path("logos/team_logos/brownseakc.png")
    if direct_logo_path.exists():
        log.info(f"Found direct league logo: {direct_logo_path}")
        # Set it directly since we know where it is
        ctx["_LEAGUE_LOGO_PATH"] = str(direct_logo_path)
        return
    
    # Check other possible locations
    possible_paths = [
        Path("logos/team_logos/brownseakc.png"),
        Path("logos/league_logos/brownseakc.png"), 
        Path("logos/brownseakc.png"),
        Path("./logos/team_logos/brownseakc.png"),
    ]
    
    for path in possible_paths:
        if path.exists():
            log.info(f"Found league logo at: {path}")
            ctx["_LEAGUE_LOGO_PATH"] = str(path)
            return
            
    log.warning(f"Could not find brownseakc.png in any expected location")


def _attach_images(ctx: Dict[str, Any], doc: DocxTemplate) -> None:
    """Attach logos with fixed league logo handling"""
    league_name = str(ctx.get("LEAGUE_NAME") or "")
    sponsor_name = str(ctx.get("SPONSOR_NAME") or "Gridiron Gazette")

    # League logo - with direct path fix
    try:
        # First try the direct path fix
        direct_path = ctx.get("_LEAGUE_LOGO_PATH")
        if direct_path and Path(direct_path).exists():
            lg = logos.sanitize_logo_for_docx(direct_path)
            if lg and Path(lg).exists():
                ctx["LEAGUE_LOGO"] = InlineImage(doc, lg, width=Mm(25))
                log.info(f"League logo attached from direct path: {direct_path}")
                return
        
        # Fall back to normal resolution
        lg_raw = logos.league_logo(league_name)
        if lg_raw:
            lg = logos.sanitize_logo_for_docx(lg_raw)
            if lg and Path(lg).exists():
                ctx["LEAGUE_LOGO"] = InlineImage(doc, lg, width=Mm(25))
                log.info(f"League logo attached via resolver: {lg}")
            else:
                log.warning(f"League logo sanitization failed: {lg_raw}")
        else:
            log.warning(f"No league logo found for: {league_name}")
    except Exception as e:
        log.error(f"Error attaching league logo: {e}")

    # Sponsor logo (unchanged)
    try:
        sp_raw = logos.sponsor_logo(sponsor_name)
        if sp_raw:
            sp = logos.sanitize_logo_for_docx(sp_raw)
            if sp and Path(sp).exists():
                ctx["SPONSOR_LOGO"] = InlineImage(doc, sp, width=Mm(25))
                log.info(f"Sponsor logo attached: {sp}")
            else:
                log.warning(f"Sponsor logo sanitization failed: {sp_raw}")
        else:
            log.warning(f"No sponsor logo found for: {sponsor_name}")
    except Exception as e:
        log.error(f"Error attaching sponsor logo: {e}")

    # Team logos (unchanged)
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
            except Exception as e:
                log.error(f"Error attaching away logo {i}: {e}")


def render_docx(template_path: str, outdocx: str, context: Dict[str, Any]) -> str:
    """Render DOCX with exact template variable matching + blurb support"""
    log.info(f"Rendering DOCX from template: {template_path}")
    log.info(f"Output path: {outdocx}")
    
    if not Path(template_path).exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    
    try:
        doc = DocxTemplate(template_path)
        log.info("Template loaded successfully")
        
        # Process context with comprehensive variable generation
        log.info("Creating basic aliases...")
        _make_basic_aliases(context)
        
        log.info("Fixing league logo resolution...")
        _fix_league_logo_resolution(context)
        
        log.info("Injecting EXACT template variables + blurbs...")
        _inject_exact_template_variables(
            context, 
            style=context.get("BLURB_STYLE", "sabre"), 
            words=int(context.get("BLURB_WORDS", 200))
        )
        
        log.info("Attaching images...")
        _attach_images(context, doc)
        
        # Log final variable summary
        total_vars = len(context)
        template_vars = len([k for k in context.keys() if any(x in k for x in ["_TOP_", "_BUST", "_DEF", "_KEYPLAY"])])
        blurb_vars = len([k for k in context.keys() if "BLURB" in k])
        
        log.info(f"Final context: {total_vars} total vars, {template_vars} template vars, {blurb_vars} blurb vars")
        
        # Show key variables for verification
        log.info("Key template variables:")
        for i in range(1, min(3, 6)):  # Show first 2 matchups
            if f"MATCHUP{i}_HOME" in context:
                log.info(f"  MATCHUP{i}_TOP_HOME = '{context.get(f'MATCHUP{i}_TOP_HOME', 'NOT SET')}'")
                log.info(f"  MATCHUP{i}_BLURB = '{context.get(f'MATCHUP{i}_BLURB', 'NOT SET')[:50]}...'")
        
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
    """Build weekly recap with exact template matching + comprehensive blurb support"""
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
        
        # Render the document
        result = render_docx(template, out_path, ctx)
        log.info(f"Weekly recap completed successfully: {result}")
        return result
        
    except Exception as e:
        log.error(f"Failed to build weekly recap: {e}")
        raise