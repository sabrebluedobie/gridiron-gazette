#!/usr/bin/env python3
"""
gazette_main.py - Unified entry point for Gridiron Gazette
Handles all build scenarios with proper error handling and debugging
"""
import os
import sys
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import our modules
try:
    import weekly_recap
    import gazette_data
    import storymaker
except ImportError as e:
    print(f"❌ Missing required module: {e}")
    print("Make sure all gazette modules are in the same directory")
    sys.exit(1)

def setup_logging(verbose=False):
    """Configure logging to both file and console"""
    level = logging.DEBUG if verbose else logging.INFO
    
    # Create logs directory if it doesn't exist
    Path('logs').mkdir(exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/gazette.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )

def validate_environment():
    """Check required environment variables and files"""
    issues = []
    warnings = []
    
    # Check ESPN credentials
    s2 = os.getenv('ESPN_S2') or os.getenv('S2')
    swid = os.getenv('SWID') or os.getenv('ESPN_SWID')
    
    if not s2:
        issues.append("Missing ESPN_S2 (or S2) cookie - required for ESPN API")
    if not swid:
        issues.append("Missing SWID (or ESPN_SWID) cookie - required for ESPN API")
    
    # Check required files
    required_files = ['recap_template.docx']
    for file in required_files:
        if not Path(file).exists():
            issues.append(f"Missing required file: {file}")
    
    # Check optional files
    optional_files = ['team_logos.json', 'gazette.yml']
    for file in optional_files:
        if not Path(file).exists():
            warnings.append(f"Optional file missing: {file} (will use defaults)")
    
    # Check OpenAI key if blurbs will be used
    if not os.getenv('OPENAI_API_KEY'):
        warnings.append("Missing OPENAI_API_KEY (LLM blurbs will be disabled)")
    
    return issues, warnings

def create_required_directories():
    """Create necessary directories"""
    dirs = [
        'recaps',
        'logs', 
        'logos/team_logos',
        'logos/league_logos',
        'logos/sponsor_logos'
    ]
    
    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

def create_default_files():
    """Create default configuration files if they don't exist"""
    import json
    
    # Default team logos mapping
    if not Path('team_logos.json').exists():
        default_logos = {
            "LEAGUE_LOGO": "logos/team_logos/league.png",
            "SPONSOR_LOGO": "logos/team_logos/gazette_logo.png"
        }
        with open('team_logos.json', 'w') as f:
            json.dump(default_logos, f, indent=2)
        print("✅ Created default team_logos.json")

def calculate_current_week():
    """Calculate current fantasy week based on season start"""
    # Default fantasy season start (adjust as needed)
    season_start = os.getenv('FANTASY_SEASON_START', '2025-09-02')
    
    try:
        start_date = datetime.strptime(season_start, '%Y-%m-%d')
        current_date = datetime.now()
        days_diff = (current_date - start_date).days
        week = min(18, max(1, (days_diff // 7) + 1))
        return week
    except:
        return 1

def test_api_connections(league_id, year, week):
    """Test ESPN API and OpenAI connections"""
    logger = logging.getLogger('test_api')
    success_count = 0
    total_tests = 3
    
    print("\n🧪 Testing API Connections")
    print("=" * 50)
    
    # Test ESPN API Basic Connection
    try:
        from espn_api.football import League
        s2 = os.getenv('ESPN_S2') or os.getenv('S2')
        swid = os.getenv('SWID') or os.getenv('ESPN_SWID')
        
        logger.info("Testing ESPN API basic connection...")
        league = League(league_id=league_id, year=year, espn_s2=s2, swid=swid)
        teams = league.teams
        logger.info(f"✅ ESPN API: Connected to league '{league.settings.name}' with {len(teams)} teams")
        print(f"✅ ESPN API: Connected to '{league.settings.name}' ({len(teams)} teams)")
        success_count += 1
        
    except Exception as e:
        logger.error(f"❌ ESPN API basic connection failed: {e}")
        print(f"❌ ESPN API: {e}")
    
    # Test ESPN Scoreboard
    try:
        logger.info(f"Testing ESPN scoreboard for week {week}...")
        scoreboard = league.scoreboard(week)
        logger.info(f"✅ ESPN Scoreboard: Found {len(scoreboard)} matchups for week {week}")
        print(f"✅ ESPN Scoreboard: {len(scoreboard)} matchups found for week {week}")
        
        # Show sample game data
        if scoreboard:
            sample_game = scoreboard[0]
            home_team = sample_game.home_team.team_name if hasattr(sample_game.home_team, 'team_name') else 'Home'
            away_team = sample_game.away_team.team_name if hasattr(sample_game.away_team, 'team_name') else 'Away'
            print(f"   Sample: {home_team} ({sample_game.home_score}) vs {away_team} ({sample_game.away_score})")
        
        success_count += 1
        
    except Exception as e:
        logger.error(f"❌ ESPN Scoreboard failed: {e}")
        print(f"❌ ESPN Scoreboard: {e}")
    
    # Test OpenAI API
    try:
        if os.getenv('OPENAI_API_KEY'):
            logger.info("Testing OpenAI API...")
            test_messages = [{"role": "user", "content": "Respond with exactly: 'API test successful'"}]
            result = storymaker._call_openai(test_messages)
            logger.info(f"✅ OpenAI API: {result}")
            print(f"✅ OpenAI API: Connected and responding")
            success_count += 1
        else:
            logger.warning("⚠️ OpenAI API: No API key set")
            print("⚠️ OpenAI API: No API key provided (LLM blurbs disabled)")
    except Exception as e:
        logger.error(f"❌ OpenAI API failed: {e}")
        print(f"❌ OpenAI API: {e}")
    
    print("=" * 50)
    print(f"API Test Results: {success_count}/{total_tests} successful")
    
    if success_count == 0:
        print("❌ No APIs are working. Check your credentials and network connection.")
        return False
    elif success_count < total_tests:
        print("⚠️ Some APIs have issues. Gazette may work with limited functionality.")
        return True
    else:
        print("✅ All APIs working correctly!")
        return True

def debug_analyze(league_id, year, week):
    """Analyze and debug the data pipeline"""
    logger = logging.getLogger('debug')
    
    print("\n🔍 Debug Analysis")
    print("=" * 50)
    
    try:
        # Test data fetch
        logger.info("Fetching league data...")
        context = gazette_data.assemble_context(str(league_id), year, week)
        
        print(f"League: {context.get('LEAGUE_NAME')}")
        print(f"Week: {context.get('WEEK_NUMBER')}")
        print(f"Games found: {len(context.get('GAMES', []))}")
        print()
        
        # Show game details
        games = context.get('GAMES', [])
        if games:
            print("Game Details:")
            for i, game in enumerate(games, 1):
                home = game.get('HOME_TEAM_NAME', 'Unknown')
                away = game.get('AWAY_TEAM_NAME', 'Unknown')
                home_score = game.get('HOME_SCORE', '0')
                away_score = game.get('AWAY_SCORE', '0')
                print(f"  {i}. {home} ({home_score}) vs {away} ({away_score})")
        else:
            print("❌ No games found!")
            return False
        
        print()
        
        # Show awards
        print("Weekly Awards:")
        print(f"  Cupcake (Lowest Score): {context.get('CUPCAKE', 'Not calculated')}")
        print(f"  Kitty (Biggest Loss): {context.get('KITTY', 'Not calculated')}")
        print(f"  Top Score: {context.get('TOPSCORE', 'Not calculated')}")
        
        print("\n✅ Data pipeline working correctly!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Debug analysis failed: {e}")
        print(f"❌ Debug analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    parser = argparse.ArgumentParser(
        description='Build Gridiron Gazette - Fantasy Football Newsletter',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 887998 2025 3                    # Basic build
  %(prog)s 887998 2025 3 --llm-blurbs       # With AI commentary  
  %(prog)s 887998 2025 3 --test-api         # Test connections
  %(prog)s 887998 2025 3 --debug            # Debug mode
        """
    )
    
    parser.add_argument('league_id', type=int, help='ESPN League ID')
    parser.add_argument('year', type=int, help='Season year')
    parser.add_argument('week', type=int, nargs='?', help='Week number (optional - will auto-detect if omitted)')
    
    parser.add_argument('--template', default='recap_template.docx', help='Template file path')
    parser.add_argument('--output', default='recaps/Week{week}_Gazette.docx', help='Output file path (supports {week}, {year}, {league} tokens)')
    
    parser.add_argument('--llm-blurbs', action='store_true', help='Generate AI-powered game commentary')
    parser.add_argument('--style', default='sabre', choices=['sabre', 'neutral', 'hype'], help='Commentary style')
    parser.add_argument('--blurb-words', type=int, default=200, help='Target words per game recap')
    
    parser.add_argument('--verbose', action='store_true', help='Verbose logging')
    parser.add_argument('--debug', action='store_true', help='Debug mode - analyze data pipeline only')
    parser.add_argument('--test-api', action='store_true', help='Test API connections only')
    
    # Parse arguments
    args = parser.parse_args()
    
    # If week not provided, calculate current week
    if args.week is None:
        args.week = calculate_current_week()
        print(f"🗓️ Auto-detected current week: {args.week}")
    
    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger('gazette_main')
    
    print("🏈 GRIDIRON GAZETTE BUILDER")
    print("=" * 50)
    print(f"League ID: {args.league_id}")
    print(f"Year: {args.year}")
    print(f"Week: {args.week}")
    if args.llm_blurbs:
        print(f"Style: {args.style} (AI-powered)")
    print()
    
    # Create required directories and files
    create_required_directories()
    create_default_files()
    
    # Validate environment
    issues, warnings = validate_environment()
    
    if warnings:
        logger.warning("Environment warnings:")
        for warning in warnings:
            logger.warning(f"  - {warning}")
        print()
    
    if issues:
        logger.error("Critical environment issues found:")
        for issue in issues:
            logger.error(f"  - {issue}")
        print("\n❌ Cannot proceed due to missing requirements.")
        print("Please check the .env.example file for required setup.")
        sys.exit(1)
    
    # Handle special modes
    if args.test_api:
        success = test_api_connections(args.league_id, args.year, args.week)
        sys.exit(0 if success else 1)
    
    if args.debug:
        success = debug_analyze(args.league_id, args.year, args.week)
        sys.exit(0 if success else 1)
    
    # Build the gazette
    print("🚀 Building Gazette...")
    print("=" * 50)
    
    try:
        output_path = weekly_recap.build_weekly_recap(
            league=None,  # Let gazette_data create the league object
            league_id=args.league_id,
            year=args.year,
            week=args.week,
            template=args.template,
            output_dir=args.output,
            llm_blurbs=args.llm_blurbs,
            blurb_style=args.style,
            blurb_words=args.blurb_words
        )
        
        # Success!
        file_size = Path(output_path).stat().st_size / 1024  # KB
        print("\n" + "=" * 50)
        print("✅ GAZETTE BUILT SUCCESSFULLY!")
        print(f"📄 Output file: {output_path}")
        print(f"📊 File size: {file_size:.1f} KB")
        
        if Path('logs/gazette.log').exists():
            print(f"📋 Detailed logs: logs/gazette.log")
        
        logger.info(f"✅ Gazette built successfully: {output_path}")
        
    except Exception as e:
        print("\n" + "=" * 50)
        print(f"❌ BUILD FAILED: {e}")
        logger.error(f"❌ Build failed: {e}")
        
        if args.verbose:
            print("\nFull error details:")
            import traceback
            traceback.print_exc()
        else:
            print("Run with --verbose for detailed error information")
        
        sys.exit(1)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹️ Build cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)