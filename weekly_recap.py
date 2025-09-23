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
        log.info("Attaching images...")
        _attach_images(context, doc)
        
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
    """Build complete weekly recap with robust error handling"""
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
        raiseUsing fallback spotlight generator")
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


def _make_aliases(ctx: Dict[str, Any]) -> None:
    """Create comprehensive aliases for template compatibility"""
    week = ctx.get("WEEK_NUMBER")
    league = ctx.get("LEAGUE_NAME") or "League"
    
    # Main title and subtitle
    ctx.setdefault("TITLE", f"Week {week} Fantasy Football Gazette — {league}")
    ctx.setdefault("SUBTITLE", "For those times when everyone wants to know your score.")

    # Scores & names aliases - support multiple naming conventions
    for i in range(1, 8):
        home_name = ctx.get(f"MATCHUP{i}_HOME", "")
        away_name = ctx.get(f"MATCHUP{i}_AWAY", "")
        home_score = ctx.get(f"MATCHUP{i}_HS", "")
        away_score = ctx.get(f"MATCHUP{i}_AS", "")
        
        # Multiple alias patterns
        aliases = {
            f"HOME{i}": home_name,
            f"AWAY{i}": away_name,
            f"HNAME{i}": home_name,
            f"ANAME{i}": away_name,
            f"HS{i}": home_score,
            f"AS{i}": away_score,
            f"HOME{i}_SCORE": home_score,
            f"AWAY{i}_SCORE": away_score,
            f"HOME{i}_NAME": home_name,
            f"AWAY{i}_NAME": away_name,
        }
        
        for alias, value in aliases.items():
            ctx.setdefault(alias, value)

        # Top-scorer aliases
        top_scorer_aliases = {
            f"TOP_SCORER_HOME_{i}": ctx.get(f"MATCHUP{i}_HOME_TOP_SCORER", ""),
            f"TOP_SCORER_AWAY_{i}": ctx.get(f"MATCHUP{i}_AWAY_TOP_SCORER", ""),
            f"TOP_POINTS_HOME_{i}": ctx.get(f"MATCHUP{i}_HOME_TOP_POINTS", ""),
            f"TOP_POINTS_AWAY_{i}": ctx.get(f"MATCHUP{i}_AWAY_TOP_POINTS", ""),
            f"HOME{i}_TOP_SCORER": ctx.get(f"MATCHUP{i}_HOME_TOP_SCORER", ""),
            f"AWAY{i}_TOP_SCORER": ctx.get(f"MATCHUP{i}_AWAY_TOP_SCORER", ""),
            f"HOME{i}_TOP_POINTS": ctx.get(f"MATCHUP{i}_HOME_TOP_POINTS", ""),
            f"AWAY{i}_TOP_POINTS": ctx.get(f"MATCHUP{i}_AWAY_TOP_POINTS", ""),
        }
        
        for alias, value in top_scorer_aliases.items():
            ctx.setdefault(alias, value)

    # Awards aliases - multiple naming patterns
    awards_base = {
        "CUPCAKE_LINE": ctx.get("CUPCAKE_LINE", "—"),
        "KITTY_LINE": ctx.get("KITTY_LINE", "—"),
        "TOPSCORE_LINE": ctx.get("TOPSCORE_LINE", "—"),
    }
    
    awards_aliases = {
        "CUPCAKE": awards_base["CUPCAKE_LINE"],
        "KITTY": awards_base["KITTY_LINE"],
        "TOPSCORE": awards_base["TOPSCORE_LINE"],
        "AWARD_CUPCAKE": awards_base["CUPCAKE_LINE"],
        "AWARD_KITTY": awards_base["KITTY_LINE"],
        "AWARD_TOPSCORE": awards_base["TOPSCORE_LINE"],
        "CUPCAKE_AWARD": awards_base["CUPCAKE_LINE"],
        "KITTY_AWARD": awards_base["KITTY_LINE"],
        "TOPSCORE_AWARD": awards_base["TOPSCORE_LINE"],
        "WEEKLY_CUPCAKE": awards_base["CUPCAKE_LINE"],
        "WEEKLY_KITTY": awards_base["KITTY_LINE"],
        "WEEKLY_TOPSCORE": awards_base["TOPSCORE_LINE"],
    }
    
    for alias, value in awards_aliases.items():
        ctx.setdefault(alias, value)

    log.debug(f"Created {len([k for k in ctx.keys() if k not in awards_base])} aliases")


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

    # Team logos
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
                        ctx[f"HOME{i}_LOGO"] = ctx[f"MATCHUP{i}_HOME_LOGO"]  # Alias
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
                        ctx[f"MATCHUP{i}_AWAY_LOGO"] = InlineImage(doc, ap, width=Mm(22))
                        ctx[f"AWAY{i}_LOGO"] = ctx[f"MATCHUP{i}_AWAY_LOGO"]  # Alias
                        log.debug(f"Away logo attached for {away_name}: {ap}")
                    else:
                        log.warning(f"Away logo sanitization failed for {away_name}: {ap_raw}")
                else:
                    log.warning(f"No away logo found for: {away_name}")
            except Exception as e:
                log.error(f"Error attaching away logo {i}: {e}")


def _inject_spotlights(ctx: Dict[str, Any], style: str, words: int) -> None:
    """
    Populate per-matchup spotlights. Uses LLM if available, otherwise stat fallback.
    Creates both generic keys and alias keys used by older templates.
    """
    log.info(f"Generating spotlights with style '{style}', target {words} words")
    
    try:
        blocks = generate_spotlights_for_week(ctx, style=style, words=words)
        log.info(f"Generated spotlights for {len(blocks)} matchups")
    except Exception as e:
        log.error(f"Failed to generate spotlights: {e}")
        blocks = {}
    
    for i in range(1, 8):
        b = blocks.get(str(i), {})
        
        # Canonical keys expected by newer templates
        spotlight_keys = {
            f"SPOTLIGHT_HOME_{i}": b.get("home", ""),
            f"SPOTLIGHT_AWAY_{i}": b.get("away", ""),
            f"SPOTLIGHT_BUST_{i}": b.get("bust", ""),
            f"SPOTLIGHT_KEYPLAY_{i}": b.get("key", ""),
            f"SPOTLIGHT_DEFNOTE_{i}": b.get("def", ""),
        }
        
        for key, value in spotlight_keys.items():
            ctx.setdefault(key, value)

        # Popular alias keys some docs use
        alias_keys = {
            f"MATCHUP{i}_SPOTLIGHT_HOME": ctx[f"SPOTLIGHT_HOME_{i}"],
            f"MATCHUP{i}_SPOTLIGHT_AWAY": ctx[f"SPOTLIGHT_AWAY_{i}"],
            f"MATCHUP{i}_SPOTLIGHT_BUST": ctx[f"SPOTLIGHT_BUST_{i}"],
            f"MATCHUP{i}_SPOTLIGHT_KEY":  ctx[f"SPOTLIGHT_KEYPLAY_{i}"],
            f"MATCHUP{i}_SPOTLIGHT_DEF":  ctx[f"SPOTLIGHT_DEFNOTE_{i}"],
            # Additional common patterns
            f"HOME{i}_SPOTLIGHT": ctx[f"SPOTLIGHT_HOME_{i}"],
            f"AWAY{i}_SPOTLIGHT": ctx[f"SPOTLIGHT_AWAY_{i}"],
            f"BUST{i}_SPOTLIGHT": ctx[f"SPOTLIGHT_BUST_{i}"],
            f"KEY{i}_SPOTLIGHT": ctx[f"SPOTLIGHT_KEYPLAY_{i}"],
            f"DEF{i}_SPOTLIGHT": ctx[f"SPOTLIGHT_DEFNOTE_{i}"],
        }
        
        for key, value in alias_keys.items():
            ctx.setdefault(key, value)

    log.debug(f"Injected spotlights with {len([k for k in ctx.keys() if 'SPOTLIGHT' in k])} spotlight keys")


def render_docx(template_path: str, outdocx: str, context: Dict[str, Any]) -> str:
    """Render the complete DOCX with all enhancements"""
    log.info(f"Rendering DOCX from template: {template_path}")
    log.info(f"Output path: {outdocx}")
    
    if not Path(template_path).exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    
    try:
        doc = DocxTemplate(template_path)
        log.info("Template loaded successfully")
        
        # Process context step by step
        log.info("Creating aliases...")
        _make_aliases(context)
        
        log.info("Injecting spotlights...")
        _inject_spotlights(
            context, 
            style=context.get("BLURB_STYLE", "sabre"), 
            words=int(context.get("BLURB_WORDS", 200))
        )
        
        log.info("