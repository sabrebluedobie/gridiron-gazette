#!/usr/bin/env python3
"""
Build Gazette - Main entry point for generating Gridiron Gazette
Updated to use HTML template and PDF output
"""
from __future__ import annotations
import os
import sys
import argparse
import logging
from datetime import datetime
from pathlib import Path

# Optional .env for local runs
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Our builder - now uses HTML/PDF version
import weekly_recap

log = logging.getLogger("build_gazette")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build a Gridiron Gazette PDF for a single week.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--league-id",
                   type=int,
                   default=int(os.getenv("LEAGUE_ID", "0")),
                   help="ESPN League ID (or set LEAGUE_ID)")
    p.add_argument("--year",
                   type=int,
                   default=int(os.getenv("YEAR", datetime.now().year)),
                   help="Season year (or set YEAR)")
    p.add_argument("--week",
                   type=int,
                   default=None,
                   help="Week number; if omitted uses league.current_week")
    p.add_argument("--template",
                   default=os.getenv("TEMPLATE", "templates/recap_template.html"),
                   help="Path to the HTML template")
    p.add_argument("--output",
                   default=os.getenv("OUTPUT", "recaps/Gazette_{year}_W{week02}.pdf"),
                   help="Output path pattern; supports {year} {week} {week02}")
    
    llm = p.add_mutually_exclusive_group()
    llm.add_argument("--llm-blurbs", action="store_true",
                     help="Enable Sabre LLM recaps (200–250 words)")
    llm.add_argument("--no-llm", dest="llm_blurbs", action="store_false",
                     help="Disable LLM (use simple fallback blurbs)")
    p.set_defaults(llm_blurbs=bool(os.getenv("LLM_BLURBS", "1") != "0"))
    
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    p.add_argument("--debug", action="store_true", help="Print traceback on failure")
    p.add_argument("--verify", action="store_true", help="Verify setup and exit")
    
    return p.parse_args(argv)


def verify_environment():
    """Verify that all required components are available"""
    
    issues = []
    
    # Check for ESPN credentials
    if not os.getenv("ESPN_S2"):
        issues.append("ESPN_S2 environment variable not set")
    if not os.getenv("SWID") and not os.getenv("ESPN_SWID"):
        issues.append("SWID/ESPN_SWID environment variable not set")
    
    # Check for template
    template_paths = [
        Path("templates/recap_template.html"),
        Path("recap_template.html"),
    ]
    
    template_found = any(p.exists() for p in template_paths)
    if not template_found:
        issues.append("HTML template not found (recap_template.html)")
    
    # Check for team_logos.json
    if not Path("team_logos.json").exists():
        log.warning("team_logos.json not found - logos will be skipped")
    
    # Check for Python packages
    try:
        import jinja2
    except ImportError:
        issues.append("jinja2 not installed (pip install jinja2)")
    
    # Check for PDF generation - WeasyPrint preferred, pdfkit as fallback
    pdf_available = False
    try:
        import weasyprint
        pdf_available = True
    except ImportError:
        try:
            import pdfkit
            pdfkit.configuration()
            pdf_available = True
        except Exception:
            pass
    
    if not pdf_available:
        issues.append("No PDF generator found. Install weasyprint: pip install weasyprint")
    
    if issues:
        log.error("Setup issues found:")
        for issue in issues:
            log.error(f"  ❌ {issue}")
        return False  # This return is INSIDE the function
    
    log.info("✅ Environment verification passed")
    return True  # This return is INSIDE the function


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    
    if args.verbose:
        log.setLevel(logging.DEBUG)
        logging.getLogger("weekly_recap").setLevel(logging.DEBUG)
    
    # Verify setup if requested
    if args.verify:
        if verify_environment():
            weekly_recap.verify_setup()
        sys.exit(0)
    
    # Validate required arguments
    if not args.league_id:
        log.error("Missing --league-id (or LEAGUE_ID environment variable)")
        sys.exit(2)
    if not args.year:
        log.error("Missing --year (or YEAR environment variable)")
        sys.exit(2)
    
    # Check template existence
    tpl = Path(args.template)
    if not tpl.exists():
        # Try alternate locations
        alt_paths = [
            Path("templates") / "recap_template.html",
            Path("recap_template.html"),
        ]
        for alt in alt_paths:
            if alt.exists():
                tpl = alt
                log.info(f"Using template: {tpl}")
                break
        else:
            log.error(f"Template not found: {args.template}")
            log.error("Save the HTML template as templates/recap_template.html")
            sys.exit(2)
    
    # Verify environment before running
    if not verify_environment():
        log.error("Please fix the setup issues before running")
        sys.exit(2)
    
    # Build the gazette
    try:
        log.info(f"Building Gazette for League {args.league_id}, Year {args.year}")
        
        out_path = weekly_recap.build_weekly_recap(
            league_id=int(args.league_id),
            year=int(args.year),
            week=args.week,
            template=str(tpl),
            output_path=str(args.output),
            use_llm_blurbs=bool(args.llm_blurbs),
        )
        
        log.info(f"✅ Gazette built successfully: {out_path}")
        
        # Show file size
        file_size = Path(out_path).stat().st_size / 1024  # KB
        if file_size > 1024:
            log.info(f"📄 File size: {file_size/1024:.1f} MB")
        else:
            log.info(f"📄 File size: {file_size:.1f} KB")
        
    except KeyboardInterrupt:
        log.error("❌ Build interrupted")
        sys.exit(130)
    except Exception as e:
        log.error(f"❌ Build failed: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()