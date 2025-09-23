#!/usr/bin/env python3
"""
gazette_main.py - Main script integrating all enhanced components
Use this to test and run your Gridiron Gazette with robust error handling
"""

import logging
import sys
import argparse
from pathlib import Path
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('gazette.log')
    ]
)
logger = logging.getLogger(__name__)

def setup_environment():
    """Setup and validate the environment"""
    logger.info("Setting up Gridiron Gazette environment...")
    
    # Validate logo setup
    try:
        from logo_resolver import validate_logo_setup, create_default_logos
        
        status = validate_logo_setup()
        logger.info("Logo setup validation completed")
        
        # Create defaults if needed
        missing_defaults = [k for k, v in status["defaults"].items() if not v["exists"]]
        if missing_defaults:
            logger.info(f"Creating missing default logos: {missing_defaults}")
            create_default_logos()
        
    except ImportError:
        logger.warning("Enhanced logo resolver not available, using original")
    except Exception as e:
        logger.error(f"Error in logo setup: {e}")
    
    # Validate required directories
    required_dirs = ["recaps", "logos", "templates"]
    for dir_name in required_dirs:
        dir_path = Path(dir_name)
        if not dir_path.exists():
            logger.info(f"Creating directory: {dir_path}")
            dir_path.mkdir(parents=True, exist_ok=True)

def test_api_connection(league_id: str, year: int, week: int) -> bool:
    """Test ESPN API connection and data availability"""
    logger.info(f"Testing API connection for League {league_id}, Year {year}, Week {week}")
    
    try:
        from espn_api.football import League
        league = League(league_id=int(league_id), year=year)
        logger.info("League object created successfully")
        
        # Test basic league info
        if hasattr(league, 'settings') and hasattr(league.settings, 'name'):
            logger.info(f"League name: {league.settings.name}")
        
        # Test scoreboard access
        try:
            scoreboard = league.scoreboard(week)
            if scoreboard:
                logger.info(f"Scoreboard accessible: {len(scoreboard)} matchups found")
                
                # Test first matchup
                if len(scoreboard) > 0:
                    matchup = scoreboard[0]
                    home_team = getattr(matchup, 'home_team', None)
                    away_team = getattr(matchup, 'away_team', None)
                    
                    if home_team and away_team:
                        home_name = getattr(home_team, 'team_name', 'Unknown')
                        away_name = getattr(away_team, 'team_name', 'Unknown')
                        logger.info(f"Sample matchup: {home_name} vs {away_name}")
                    else:
                        logger.warning("Team data missing in sample matchup")
                
                return True
            else:
                logger.error("Empty scoreboard returned")
                return False
                
        except Exception as e:
            logger.error(f"Scoreboard access failed: {e}")
            return False
            
    except Exception as e:
        logger.error(f"League connection failed: {e}")
        return False

def run_debug_analysis(league_id: str, year: int, week: int):
    """Run comprehensive debug analysis"""
    logger.info("Running debug analysis...")
    
    try:
        # Use the debug helper if available
        try:
            from debug_espn_api import debug_league_data, test_api_robustness
            from espn_api.football import League
            
            league = League(league_id=int(league_id), year=year)
            
            # Run comprehensive debug
            debug_league_data(league, year, week, f"debug_league_{league_id}_week_{week}.json")
            
            # Test multiple weeks if requested
            weeks_to_test = [max(1, week-1), week, min(17, week+1)]
            test_api_robustness(league, year, weeks_to_test, delay=1.0)
            
        except ImportError:
            logger.warning("Debug helper not available")
            
    except Exception as e:
        logger.error(f"Debug analysis failed: {e}")

def build_gazette(league_id: str, year: int, week: int, 
                 template: Optional[str] = None, 
                 output_dir: str = "recaps",
                 llm_blurbs: bool = False,
                 style: str = "sabre") -> Optional[str]:
    """Build the gazette with enhanced error handling"""
    
    logger.info(f"Building gazette for League {league_id}, Week {week}")
    
    try:
        # Import required modules
        from espn_api.football import League
        league = League(league_id=int(league_id), year=year)
        
        # Try to use enhanced weekly_recap if available
        try:
            from weekly_recap import build_weekly_recap
            logger.info("Using enhanced weekly recap builder")
        except ImportError:
            # Fall back to original
            from weekly_recap import build_weekly_recap
            logger.info("Using original weekly recap builder")
        
        # Build the recap
        output_path = build_weekly_recap(
            league=league,
            league_id=int(league_id),
            year=year,
            week=week,
            template=template,
            output_dir=output_dir,
            llm_blurbs=llm_blurbs,
            blurb_style=style,
            blurb_words=200
        )
        
        logger.info(f"Gazette built successfully: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Failed to build gazette: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None

def main():
    """Main entry point with command line interface"""
    
    parser = argparse.ArgumentParser(description="Gridiron Gazette - Fantasy Football Newsletter Generator")
    parser.add_argument("league_id", help="ESPN League ID")
    parser.add_argument("year", type=int, help="Season year")
    parser.add_argument("week", type=int, help="Week number")
    parser.add_argument("--template", help="Path to Word template file")
    parser.add_argument("--output", default="recaps", help="Output directory or filename pattern")
    parser.add_argument("--llm-blurbs", action="store_true", help="Generate LLM-powered blurbs")
    parser.add_argument("--style", default="sabre", help="Blurb style (sabre, casual, etc.)")
    parser.add_argument("--debug", action="store_true", help="Run debug analysis")
    parser.add_argument("--test-api", action="store_true", help="Test API connection only")
    parser.add_argument("--setup", action="store_true", help="Setup environment only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("Verbose logging enabled")
    
    # Setup environment
    if args.setup:
        setup_environment()
        print("Environment setup complete")
        return
    
    # Validate arguments
    if not args.league_id.isdigit():
        logger.error("League ID must be numeric")
        sys.exit(1)
    
    if args.year < 2000 or args.year > 2030:
        logger.error("Year must be between 2000 and 2030")
        sys.exit(1)
    
    if args.week < 1 or args.week > 18:
        logger.error("Week must be between 1 and 18")
        sys.exit(1)
    
    # Setup environment first
    setup_environment()
    
    # Test API connection
    if args.test_api or args.debug:
        if not test_api_connection(args.league_id, args.year, args.week):
            logger.error("API connection test failed")
            if not args.debug:  # Continue with debug even if API test fails
                sys.exit(1)
    
    # Run debug analysis
    if args.debug:
        run_debug_analysis(args.league_id, args.year, args.week)
        return
    
    # Build the gazette
    output_path = build_gazette(
        league_id=args.league_id,
        year=args.year,
        week=args.week,
        template=args.template,
        output_dir=args.output,
        llm_blurbs=args.llm_blurbs,
        style=args.style
    )
    
    if output_path:
        print(f"\n✅ Gazette built successfully!")
        print(f"📄 Output file: {output_path}")
        
        # Provide next steps
        print(f"\nNext steps:")
        print(f"1. Open {output_path} in Microsoft Word")
        print(f"2. Review and edit the content as needed")
        print(f"3. Save or export as PDF for distribution")
        
        # Show file size
        try:
            file_size = Path(output_path).stat().st_size
            print(f"📊 File size: {file_size / 1024:.1f} KB")
        except Exception:
            pass
            
    else:
        print("\n❌ Failed to build gazette")
        print("Check the logs above for error details")
        sys.exit(1)

def quick_build(league_id: str, year: int, week: int, **kwargs):
    """Convenience function for programmatic usage"""
    setup_environment()
    return build_gazette(league_id, year, week, **kwargs)

def batch_build(league_id: str, year: int, weeks: list, **kwargs):
    """Build multiple weeks at once"""
    setup_environment()
    results = {}
    
    logger.info(f"Building gazette for {len(weeks)} weeks")
    
    for week in weeks:
        logger.info(f"Processing week {week}...")
        try:
            output_path = build_gazette(league_id, year, week, **kwargs)
            results[week] = output_path
            if output_path:
                logger.info(f"Week {week} completed: {output_path}")
            else:
                logger.error(f"Week {week} failed")
        except Exception as e:
            logger.error(f"Week {week} error: {e}")
            results[week] = None
    
    return results

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)

# Example usage functions for testing
def example_usage():
    """Example usage patterns"""
    
    # Single week build
    output = quick_build("123456", 2024, 5)
    
    # Batch build multiple weeks
    outputs = batch_build("123456", 2024, [3, 4, 5], 
                         llm_blurbs=True, 
                         output_dir="batch_recaps")
    
    # Custom output filename pattern
    output = quick_build("123456", 2024, 5, 
                        output_dir="custom_recaps/{league}_week_{week02}_{year}.docx")

def troubleshooting_guide():
    """Print troubleshooting guide"""
    print("""
🔧 TROUBLESHOOTING GUIDE

Common Issues and Solutions:

1. "No scoreboard data available"
   - ESPN API may be down or rate limiting
   - Try again in a few minutes
   - Use --debug flag to see detailed API responses
   
2. "Template file not found"
   - Ensure recap_template.docx exists in project directory
   - Use --template flag to specify custom template path
   
3. "Missing team logos" 
   - Run with --setup to create default logos
   - Add team logos to logos/team_logos/ directory
   - Update team_logos.json mapping file
   
4. "LLM blurb generation failed"
   - Check OpenAI API key in environment
   - Ensure storymaker module is properly configured
   - Try without --llm-blurbs flag for basic recaps
   
5. "Partial or missing player data"
   - ESPN API may not have complete data for recent weeks
   - Try a completed week (not current week)
   - Use --debug to analyze what data is available

🔍 Debug Commands:
   python gazette_main.py 123456 2024 5 --debug
   python gazette_main.py 123456 2024 5 --test-api
   python gazette_main.py 123456 2024 5 --verbose

📁 Required Files:
   - recap_template.docx (Word template)
   - logos/team_logos/ (team logo images)  
   - team_logos.json (team logo mappings)
   
📧 For additional help, check the logs in gazette.log
    """)

# Add troubleshooting command
if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "help":
    troubleshooting_guide()