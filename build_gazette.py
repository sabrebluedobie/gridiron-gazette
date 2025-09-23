#!/usr/bin/env python3
import os
import sys
import logging
from datetime import datetime
from pathlib import Path
import argparse

# ✨ Load .env so local runs pick up ESPN_S2 / SWID / TEAM_LOGOS_FILE, etc.
try:
    from dotenv import load_dotenv  # python-dotenv
    load_dotenv()
    print("✅ Environment loaded")
except Exception as e:
    print(f"⚠️  No .env loading: {e}")

import weekly_recap

# Set up logging
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("build_gazette")

def get_env(name: str, default: str | None = None) -> str | None:
    """Get environment variable with fallback"""
    v = os.getenv(name)
    return v if (v and str(v).strip()) else default

def parse_args() -> argparse.Namespace:
    """Parse command line arguments"""
    p = argparse.ArgumentParser(
        "Gridiron Gazette builder",
        description="Generate weekly fantasy football recaps with Sabre's witty commentary"
    )
    
    p.add_argument("--league", "--league-id", dest="league_id",
                   type=int, default=int(get_env("LEAGUE_ID") or 0),
                   help="ESPN League ID (or set LEAGUE_ID env)")
    
    p.add_argument("--year", type=int,
                   default=int(get_env("YEAR") or datetime.now().year),
                   help="Season year (or set YEAR env)")
    
    p.add_argument("--week", type=int, default=None, 
                   help="Week number (auto-detects current week if not specified)")

    p.add_argument("--template", default=get_env("TEMPLATE") or "recap_template.docx",
                   help="Path to .docx template (or TEMPLATE env)")
    
    p.add_argument("--outdocx", default=get_env("OUTDOCX") or "recaps/Week{week}_Gazette.docx",
                   help="Output file path (supports tokens {week},{week02},{year},{league})")

    # Sabre blurbs - default ON, as specified
    p.add_argument("--llm-blurbs", dest="llm_blurbs", action="store_true",
                   default=True, help="Generate Sabre blurbs (default ON)")
    p.add_argument("--no-blurbs", dest="llm_blurbs", action="store_false",
                   help="Disable LLM blurbs")
    
    p.add_argument("--blurb-style", default=get_env("BLURB_STYLE") or "sabre",
                   choices=["sabre", "neutral", "hype"],
                   help="Blurb voice/style (default: sabre)")
    
    p.add_argument("--blurb-words", type=int, default=int(get_env("BLURB_WORDS") or 200),
                   help="Target words per blurb (default: 200)")

    p.add_argument("--verbose", "-v", action="store_true", 
                   default=("true" == str(get_env("VERBOSE", "")).lower()),
                   help="Enable verbose logging")
    
    p.add_argument("--debug", action="store_true",
                   help="Enable debug-level logging")
    
    return p.parse_args()

def preflight_check(args: argparse.Namespace) -> bool:
    """Perform preflight checks and log environment status"""
    log.info("🔍 Preflight Check")
    log.info("=" * 50)
    
    # Required parameters
    if not args.league_id or args.league_id <= 0:
        log.error("❌ LEAGUE_ID is required and must be > 0")
        return False
    
    if not Path(args.template).exists():
        log.error(f"❌ Template not found: {args.template}")
        return False
    
    # ESPN credentials
    espn_s2 = get_env("ESPN_S2") or get_env("S2")
    swid = get_env("SWID") or get_env("ESPN_SWID")
    
    log.info(f"📊 League ID: {args.league_id}")
    log.info(f"📅 Year: {args.year}")
    log.info(f"📖 Week: {args.week or 'auto-detect'}")
    log.info(f"📄 Template: {args.template}")
    log.info(f"💾 Output: {args.outdocx}")
    log.info(f"🔐 ESPN_S2: {'✅ present' if espn_s2 else '❌ missing'}")
    log.info(f"🔐 SWID: {'✅ present' if swid else '❌ missing'}")
    
    if not (espn_s2 and swid):
        log.error("❌ ESPN credentials (ESPN_S2 and SWID) are required")
        log.error("   Set them in your environment or .env file")
        return False
    
    # OpenAI for Sabre blurbs
    openai_key = get_env("OPENAI_API_KEY")
    log.info(f"🤖 OpenAI API: {'✅ present' if openai_key else '⚠️  missing'}")
    
    if args.llm_blurbs and not openai_key:
        log.warning("⚠️  Sabre blurbs requested but OPENAI_API_KEY missing")
        log.warning("   Will use fallback stat-based spotlights")
    
    # Logo configuration
    team_logos = get_env("TEAM_LOGOS_FILE") or "team_logos.json"
    log.info(f"🖼️  Team logos: {team_logos} {'✅' if Path(team_logos).exists() else '❌'}")
    
    # Blurb settings
    log.info(f"✍️  Sabre blurbs: {'✅ enabled' if args.llm_blurbs else '❌ disabled'}")
    log.info(f"🎭 Blurb style: {args.blurb_style}")
    log.info(f"📝 Target words: {args.blurb_words}")
    
    log.info("=" * 50)
    return True

def main():
    """Main entry point"""
    args = parse_args()

    # Configure logging
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        log.setLevel(logging.DEBUG)
    elif args.verbose:
        logging.getLogger().setLevel(logging.INFO)
        log.setLevel(logging.INFO)
    else:
        logging.getLogger().setLevel(logging.WARNING)

    log.info("🏈 Gridiron Gazette Builder")
    log.info(f"🐕 Sabre the Doberman Reporter {'is ready!' if args.llm_blurbs else 'is taking a break'}")
    
    # Preflight checks
    if not preflight_check(args):
        sys.exit(1)

    try:
        log.info("🚀 Building weekly recap...")
        
        # Build the gazette
        output_path = weekly_recap.build_weekly_recap(
            league=None,                      # weekly_recap/gazette_data will construct as needed
            league_id=int(args.league_id),
            year=int(args.year),
            week=int(args.week) if args.week is not None else 0,
            template=args.template,
            output_dir=args.outdocx,
            llm_blurbs=bool(args.llm_blurbs),     # Sabre ON by default
            blurb_style=str(args.blurb_style),    # default 'sabre'
            blurb_words=int(args.blurb_words),
        )
        
        log.info("=" * 50)
        log.info("✅ SUCCESS!")
        log.info(f"📄 Recap generated: {output_path}")
        
        # Verify output
        if Path(output_path).exists():
            size_kb = Path(output_path).stat().st_size / 1024
            log.info(f"📊 File size: {size_kb:.1f} KB")
        
        log.info("🎉 Build complete - Sabre's work is done!")
        
    except KeyboardInterrupt:
        log.error("❌ Build interrupted by user")
        sys.exit(130)
    except Exception as e:
        log.error(f"❌ Build failed: {e}")
        if args.debug:
            import traceback
            log.error("Full traceback:")
            log.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()