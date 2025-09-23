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


def _make_comprehensive_aliases(ctx: Dict[str, Any]) -> None:
    """Create EVERY possible alias pattern the template might expect"""
    week = ctx.get("WEEK_NUMBER")
    league = ctx.get("LEAGUE_NAME") or "League"
    
    # Main title and subtitle
    ctx.setdefault("TITLE", f"Week {week} Fantasy Football Gazette — {league}")
    ctx.setdefault("SUBTITLE", "For those times when everyone wants to know your score.")

    # Comprehensive team/score aliases for ALL possible patterns
    for i in range(1, 8):
        home_name = ctx.get(f"MATCHUP{i}_HOME", "")
        away_name = ctx.get(f"MATCHUP{i}_AWAY", "")
        home_score = ctx.get(f"MATCHUP{i}_HS", "")
        away_score = ctx.get(f"MATCHUP{i}_AS", "")
        home_top_scorer = ctx.get(f"MATCHUP{i}_HOME_TOP_SCORER", "")
        home_top_points = ctx.get(f"MATCHUP{i}_HOME_TOP_POINTS", "")
        away_top_scorer = ctx.get(f"MATCHUP{i}_AWAY_TOP_SCORER", "")
        away_top_points = ctx.get(f"MATCHUP{i}_AWAY_TOP_POINTS", "")
        
        # EVERY possible naming pattern for teams/scores
        team_score_aliases = {
            # Basic patterns
            f"HOME{i}": home_name,
            f"AWAY{i}": away_name,
            f"HNAME{i}": home_name,
            f"ANAME{i}": away_name,
            f"HS{i}": home_score,
            f"AS{i}": away_score,
            
            # Extended patterns
            f"HOME{i}_NAME": home_name,
            f"AWAY{i}_NAME": away_name,
            f"HOME{i}_SCORE": home_score,
            f"AWAY{i}_SCORE": away_score,
            f"MATCHUP{i}_HOME_NAME": home_name,
            f"MATCHUP{i}_AWAY_NAME": away_name,
            f"MATCHUP{i}_HOME_SCORE": home_score,
            f"MATCHUP{i}_AWAY_SCORE": away_score,
            
            # Top scorer patterns - CRITICAL for Stats Spotlight
            f"TOP_SCORER_HOME_{i}": home_top_scorer,
            f"TOP_SCORER_AWAY_{i}": away_top_scorer,
            f"TOP_POINTS_HOME_{i}": home_top_points,
            f"TOP_POINTS_AWAY_{i}": away_top_points,
            f"HOME{i}_TOP_SCORER": home_top_scorer,
            f"AWAY{i}_TOP_SCORER": away_top_scorer,
            f"HOME{i}_TOP_POINTS": home_top_points,
            f"AWAY{i}_TOP_POINTS": away_top_points,
            f"MATCHUP{i}_HOME_TOP": home_top_scorer,
            f"MATCHUP{i}_AWAY_TOP": away_top_scorer,
            f"MATCHUP{i}_HOME_TOP_PTS": home_top_points,
            f"MATCHUP{i}_AWAY_TOP_PTS": away_top_points,
            
            # More top scorer variations
            f"TOP_HOME_{i}": home_top_scorer,
            f"TOP_AWAY_{i}": away_top_scorer,
            f"TOP_HOME_POINTS_{i}": home_top_points,
            f"TOP_AWAY_POINTS_{i}": away_top_points,
        }
        
        for alias, value in team_score_aliases.items():
            ctx.setdefault(alias, value)

    # Awards aliases - CRITICAL for Weekly Awards section
    cupcake_line = ctx.get("CUPCAKE_LINE", "—")
    kitty_line = ctx.get("KITTY_LINE", "—") 
    topscore_line = ctx.get("TOPSCORE_LINE", "—")
    
    # EVERY possible awards pattern
    awards_aliases = {
        # Basic awards
        "CUPCAKE": cupcake_line,
        "KITTY": kitty_line, 
        "TOPSCORE": topscore_line,
        
        # Award prefix patterns
        "AWARD_CUPCAKE": cupcake_line,
        "AWARD_KITTY": kitty_line,
        "AWARD_TOPSCORE": topscore_line,
        
        # Line suffix patterns  
        "CUPCAKE_AWARD": cupcake_line,
        "KITTY_AWARD": kitty_line,
        "TOPSCORE_AWARD": topscore_line,
        
        # Weekly prefix patterns
        "WEEKLY_CUPCAKE": cupcake_line,
        "WEEKLY_KITTY": kitty_line,
        "WEEKLY_TOPSCORE": topscore_line,
        
        # Individual component patterns
        "CUPCAKE_TEAM": ctx.get("AWARD_CUPCAKE_TEAM", ""),
        "CUPCAKE_SCORE": ctx.get("AWARD_CUPCAKE_SCORE", ""),
        "KITTY_WINNER": ctx.get("AWARD_KITTY_WINNER", ""),
        "KITTY_LOSER": ctx.get("AWARD_KITTY_LOSER", ""),
        "KITTY_GAP": ctx.get("AWARD_KITTY_GAP", ""),
        "TOPSCORE_TEAM": ctx.get("AWARD_TOPSCORE_TEAM", ""),
        "TOPSCORE_POINTS": ctx.get("AWARD_TOPSCORE_POINTS", ""),
        
        # Alternative patterns
        "LOWEST_SCORE": cupcake_line,
        "HIGHEST_SCORE": topscore_line,
        "BIGGEST_BLOWOUT": kitty_line,
        "WORST_PERFORMANCE": cupcake_line,
        "BEST_PERFORMANCE": topscore_line,
    }
    
    for alias, value in awards_aliases.items():
        ctx.setdefault(alias, value)

    log.info(f"Created comprehensive aliases - total context keys: {len(ctx)}")


def _inject_template_spotlight_variables(ctx: Dict[str, Any], style: str, words: int) -> None:
    """
    Generate and inject ALL possible spotlight variable patterns.
    This ensures the template finds what it's looking for regardless of naming convention.
    """
    log.info(f"Generating comprehensive spotlight variables - style: {style}, words: {words}")
    
    try:
        blocks = generate_spotlights_for_week(ctx, style=style, words=words)
        log.info(f"Generated spotlights for {len(blocks)} matchups")
        
        # Log sample spotlight content for debugging
        if blocks and "1" in blocks:
            sample = blocks["1"]
            log.info(f"Sample spotlight content: home='{sample.get('home', '')[:50]}...'")
    except Exception as e:
        log.error(f"Failed to generate spotlights: {e}")
        blocks = {}
    
    # Generate EVERY possible spotlight variable pattern
    for i in range(1, 8):
        block = blocks.get(str(i), {})
        
        home_spotlight = block.get("home", "")
        away_spotlight = block.get("away", "")
        bust_spotlight = block.get("bust", "")
        key_spotlight = block.get("key", "")
        def_spotlight = block.get("def", "")
        
        # Log what we're injecting for debugging
        if i <= 2:  # Log first 2 matchups
            log.info(f"Matchup {i} spotlight injection:")
            log.info(f"  home: '{home_spotlight[:50]}...'")
            log.info(f"  away: '{away_spotlight[:50]}...'")
        
        # ALL possible spotlight variable patterns
        spotlight_patterns = {
            # Primary patterns
            f"SPOTLIGHT_HOME_{i}": home_spotlight,
            f"SPOTLIGHT_AWAY_{i}": away_spotlight,
            f"SPOTLIGHT_BUST_{i}": bust_spotlight,
            f"SPOTLIGHT_KEYPLAY_{i}": key_spotlight,
            f"SPOTLIGHT_DEFNOTE_{i}": def_spotlight,
            f"SPOTLIGHT_KEY_{i}": key_spotlight,
            f"SPOTLIGHT_DEF_{i}": def_spotlight,
            
            # Matchup prefix patterns
            f"MATCHUP{i}_SPOTLIGHT_HOME": home_spotlight,
            f"MATCHUP{i}_SPOTLIGHT_AWAY": away_spotlight,
            f"MATCHUP{i}_SPOTLIGHT_BUST": bust_spotlight,
            f"MATCHUP{i}_SPOTLIGHT_KEY": key_spotlight,
            f"MATCHUP{i}_SPOTLIGHT_DEF": def_spotlight,
            f"MATCHUP{i}_SPOTLIGHT_KEYPLAY": key_spotlight,
            f"MATCHUP{i}_SPOTLIGHT_DEFNOTE": def_spotlight,
            
            # Short patterns
            f"HOME{i}_SPOTLIGHT": home_spotlight,
            f"AWAY{i}_SPOTLIGHT": away_spotlight,
            f"BUST{i}_SPOTLIGHT": bust_spotlight,
            f"KEY{i}_SPOTLIGHT": key_spotlight,
            f"DEF{i}_SPOTLIGHT": def_spotlight,
            
            # Alternative patterns
            f"HOME_SPOTLIGHT_{i}": home_spotlight,
            f"AWAY_SPOTLIGHT_{i}": away_spotlight,
            f"BUST_SPOTLIGHT_{i}": bust_spotlight,
            f"KEY_SPOTLIGHT_{i}": key_spotlight,
            f"DEF_SPOTLIGHT_{i}": def_spotlight,
            
            # Descriptive patterns
            f"TOP_SCORER_HOME_SPOTLIGHT_{i}": home_spotlight,
            f"TOP_SCORER_AWAY_SPOTLIGHT_{i}": away_spotlight,
            f"BIGGEST_BUST_SPOTLIGHT_{i}": bust_spotlight,
            f"KEY_PLAY_SPOTLIGHT_{i}": key_spotlight,
            f"DEFENSE_NOTE_SPOTLIGHT_{i}": def_spotlight,
            
            # Simple patterns the template might expect
            f"HOME_TOP_SCORER_{i}": home_spotlight,
            f"AWAY_TOP_SCORER_{i}": away_spotlight,
            f"BIGGEST_BUST_{i}": bust_spotlight,
            f"KEY_PLAY_{i}": key_spotlight,
            f"DEFENSE_NOTE_{i}": def_spotlight,
        }
        
        # Inject all patterns
        for pattern, value in spotlight_patterns.items():
            ctx.setdefault(pattern, value)
    
    # Count spotlight variables for verification
    spotlight_vars = {k: v for k, v in ctx.items() if "SPOTLIGHT" in k or "BUST" in k or "KEY" in k or "DEF" in k}
    log.info(f"Injected {len(spotlight_vars)} spotlight-related variables")


def _attach_images(ctx: Dict[str, Any], doc: DocxTemplate) -> None:
    """Attach logos to context with robust resolution"""
    league_name = str(ctx.get("LEAGUE_NAME") or "")
    sponsor_name = str(ctx.get("SPONSOR_NAME") or "Gridiron Gazette")

    # League logo
    try:
        lg_raw = logos.league_logo(league_name)
        if lg_raw:
            lg = logos.sanitize_logo_for_docx(lg_raw)
            if lg and Path(lg).exists():
                ctx["LEAGUE_LOGO"] = InlineImage(doc, lg, width=Mm(25))
                log.debug(f"League logo attached: {lg}")
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
                log.debug(f"Sponsor logo attached: {sp}")
            else:
                log.warning(f"Sponsor logo sanitization failed: {sp_raw}")
        else:
            log.warning(f"No sponsor logo found for: {sponsor_name}")
    except Exception as e:
        log.error(f"Error attaching sponsor logo: {e}")

    # Team logos with comprehensive alias support
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
                        home_logo = InlineImage(doc, hp, width=Mm(22))
                        # ALL possible logo variable patterns
                        logo_patterns = [
                            f"MATCHUP{i}_HOME_LOGO", f"HOME{i}_LOGO", 
                            f"HOME_LOGO_{i}", f"LOGO_HOME_{i}"
                        ]
                        for pattern in logo_patterns:
                            ctx[pattern] = home_logo
                        log.debug(f"Home logo attached for {home_name}: {hp}")
                    else:
                        log.warning(f"Home logo sanitization failed for {home_name}: {hp_raw}")
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
                        away_logo = InlineImage(doc, ap, width=Mm(22))
                        # ALL possible logo variable patterns
                        logo_patterns = [
                            f"MATCHUP{i}_AWAY_LOGO", f"AWAY{i}_LOGO",
                            f"AWAY_LOGO_{i}", f"LOGO_AWAY_{i}"
                        ]
                        for pattern in logo_patterns:
                            ctx[pattern] = away_logo
                        log.debug(f"Away logo attached for {away_name}: {ap}")
                    else:
                        log.warning(f"Away logo sanitization failed for {away_name}: {ap_raw}")
                else:
                    log.warning(f"No away logo found for: {away_name}")
            except Exception as e:
                log.error(f"Error attaching away logo {i}: {e}")


def render_docx(template_path: str, outdocx: str, context: Dict[str, Any]) -> str:
    """Render the complete DOCX with comprehensive template variable support"""
    log.info(f"Rendering DOCX from template: {template_path}")
    log.info(f"Output path: {outdocx}")
    
    if not Path(template_path).exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    
    try:
        doc = DocxTemplate(template_path)
        log.info("Template loaded successfully")
        
        # Process context with comprehensive variable generation
        log.info("Creating comprehensive aliases...")
        _make_comprehensive_aliases(context)
        
        log.info("Injecting comprehensive spotlight variables...")
        _inject_template_spotlight_variables(
            context, 
            style=context.get("BLURB_STYLE", "sabre"), 
            words=int(context.get("BLURB_WORDS", 200))
        )
        
        log.info("Attaching images...")
        _attach_images(context, doc)
        
        # Log final context summary for debugging
        total_vars = len(context)
        spotlight_vars = len([k for k in context.keys() if "SPOTLIGHT" in k])
        award_vars = len([k for k in context.keys() if any(x in k for x in ["CUPCAKE", "KITTY", "TOPSCORE"])])
        
        log.info(f"Final context: {total_vars} total vars, {spotlight_vars} spotlight vars, {award_vars} award vars")
        
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
    """Build complete weekly recap with comprehensive template variable support"""
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