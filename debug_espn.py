#!/usr/bin/env python3
"""
Debug script to test ESPN API connection and logo discovery
"""

import json
import os
from pathlib import Path

def test_espn_connection():
    """Test ESPN API connection"""
    print("=== Testing ESPN Connection ===")
    
    try:
        # Load config
        leagues = json.loads(Path("leagues.json").read_text())
        config = leagues[0]
        print(f"League: {config['name']}")
        print(f"League ID: {config['league_id']}")
        print(f"Year: {config['year']}")
        
        # Check credentials
        espn_s2 = os.getenv("ESPN_S2") or config.get("espn_s2")
        swid = os.getenv("SWID") or config.get("swid")
        
        print(f"ESPN_S2 present: {bool(espn_s2)}")
        print(f"SWID present: {bool(swid)}")
        
        if not espn_s2 or not swid:
            print("❌ Missing ESPN credentials!")
            return False
        
        # Test ESPN API
        from espn_api.football import League
        league = League(
            league_id=config["league_id"],
            year=config["year"],
            espn_s2=espn_s2,
            swid=swid
        )
        
        print(f"✅ Connected to league: {league.settings.name}")
        print(f"Teams in league: {len(league.teams)}")
        
        for i, team in enumerate(league.teams, 1):
            print(f"  {i}. {team.team_name} (Owner: {team.owner})")
        
        # Test getting current week data
        try:
            current_week = league.current_week
            print(f"Current week: {current_week}")
            
            scoreboard = league.scoreboard(week=1)  # Test week 1
            print(f"Week 1 games: {len(scoreboard)}")
            
            for i, game in enumerate(scoreboard, 1):
                home = game.home_team.team_name if hasattr(game, 'home_team') else "Unknown"
                away = game.away_team.team_name if hasattr(game, 'away_team') else "Unknown"
                home_score = getattr(game, 'home_score', '?')
                away_score = getattr(game, 'away_score', '?')
                print(f"  Game {i}: {home} ({home_score}) vs {away} ({away_score})")
                
        except Exception as e:
            print(f"❌ Error getting scoreboard: {e}")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ ESPN connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_logo_discovery():
    """Test logo discovery system"""
    print("\n=== Testing Logo Discovery ===")
    
    try:
        from mascots_util import logo_for
        
        # Test with some common team names
        test_teams = ["Storm", "Wafflers", "Eagles", "Panthers", "Hawks"]
        
        # Add teams from ESPN if available
        try:
            leagues = json.loads(Path("leagues.json").read_text())
            config = leagues[0]
            espn_s2 = os.getenv("ESPN_S2") or config.get("espn_s2")
            swid = os.getenv("SWID") or config.get("swid")
            
            if espn_s2 and swid:
                from espn_api.football import League
                league = League(
                    league_id=config["league_id"],
                    year=config["year"],
                    espn_s2=espn_s2,
                    swid=swid
                )
                test_teams = [team.team_name for team in league.teams]
                print(f"Using ESPN team names: {test_teams}")
        except:
            print(f"Using default test teams: {test_teams}")
        
        print("\nLogo search results:")
        found_logos = 0
        for team in test_teams:
            logo_path = logo_for(team)
            if logo_path and Path(logo_path).exists():
                print(f"  ✅ {team}: {logo_path}")
                found_logos += 1
            else:
                print(f"  ❌ {team}: No logo found")
        
        print(f"\nFound logos for {found_logos}/{len(test_teams)} teams")
        
        # Check logo directories
        print("\nLogo directories:")
        logo_dirs = [
            "logos",
            "logos/team_logos", 
            "logos/generated_logos",
            "logos/ai",
            "assets/logos"
        ]
        
        for dir_path in logo_dirs:
            p = Path(dir_path)
            if p.exists():
                files = list(p.glob("*.png")) + list(p.glob("*.jpg"))
                print(f"  ✅ {dir_path}: {len(files)} image files")
            else:
                print(f"  ❌ {dir_path}: Directory not found")
        
        # Check team_logos.json
        mapping_file = Path("team_logos.json")
        if mapping_file.exists():
            try:
                mapping = json.loads(mapping_file.read_text())
                print(f"  ✅ team_logos.json: {len(mapping)} mappings")
            except Exception as e:
                print(f"  ❌ team_logos.json: Error reading - {e}")
        else:
            print("  ❌ team_logos.json: File not found")
        
        return found_logos > 0
        
    except Exception as e:
        print(f"❌ Logo discovery failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_data_pipeline():
    """Test the data pipeline"""
    print("\n=== Testing Data Pipeline ===")
    
    try:
        from gazette_data import fetch_week_from_espn, build_context
        
        # Load config
        leagues = json.loads(Path("leagues.json").read_text())
        config = leagues[0]
        
        espn_s2 = os.getenv("ESPN_S2") or config.get("espn_s2")
        swid = os.getenv("SWID") or config.get("swid")
        
        if not espn_s2 or not swid:
            print("❌ Missing ESPN credentials")
            return False
        
        # Fetch data
        games = fetch_week_from_espn(
            league_id=config["league_id"],
            year=config["year"],
            espn_s2=espn_s2,
            swid=swid,
            week=1
        )
        
        print(f"Fetched {len(games)} games")
        
        if not games:
            print("❌ No games found!")
            return False
        
        for i, game in enumerate(games, 1):
            print(f"  Game {i}: {game}")
        
        # Build context
        context = build_context(config, games)
        print(f"\nContext built with {len(context)} keys")
        print(f"Awards: {context.get('awards', {})}")
        
        return True
        
    except Exception as e:
        print(f"❌ Data pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("🔍 Debugging ESPN and Logo Integration\n")
    
    espn_ok = test_espn_connection()
    logo_ok = test_logo_discovery()
    pipeline_ok = test_data_pipeline()
    
    print(f"\n=== Summary ===")
    print(f"ESPN Connection: {'✅' if espn_ok else '❌'}")
    print(f"Logo Discovery: {'✅' if logo_ok else '❌'}")
    print(f"Data Pipeline: {'✅' if pipeline_ok else '❌'}")
    
    if not espn_ok:
        print("\n🔧 To fix ESPN connection:")
        print("1. Verify ESPN_S2 and SWID environment variables")
        print("2. Check that your league is accessible")
        print("3. Ensure espn_api package is installed")
    
    if not logo_ok:
        print("\n🔧 To fix logo discovery:")
        print("1. Run: python quick_logo_fix.py")
        print("2. Or create logos manually in logos/generated_logos/")
        print("3. Ensure team_logos.json exists with proper mappings")
    
    if all([espn_ok, logo_ok, pipeline_ok]):
        print("\n🎉 Everything looks good! Try running the gazette build now.")

if __name__ == "__main__":
    main()