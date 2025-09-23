#!/usr/bin/env python3
"""
test_awards.py - Quick test script to validate awards are working
Run this to test your awards logic before building the gazette
"""

import os
import sys
from pathlib import Path
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_awards_with_sample_data():
    """Test awards calculation with sample game data"""
    
    # Sample game data like what you'd get from ESPN
    sample_games = [
        {
            "HOME_TEAM_NAME": "Nana's Hawks",
            "AWAY_TEAM_NAME": "The Champ Big Daddy", 
            "HOME_SCORE": "95.62",
            "AWAY_SCORE": "95.64"
        },
        {
            "HOME_TEAM_NAME": "Jimmy Birds",
            "AWAY_TEAM_NAME": "Annie1235 slayy",
            "HOME_SCORE": "132.82", 
            "AWAY_SCORE": "99.14"
        },
        {
            "HOME_TEAM_NAME": "DEM BOY'S!🏆🏆🏆🏆",
            "AWAY_TEAM_NAME": "Avondale Welders",
            "HOME_SCORE": "99.78",
            "AWAY_SCORE": "82.1"
        },
        {
            "HOME_TEAM_NAME": "Phoenix Blues", 
            "AWAY_TEAM_NAME": "Kansas City Pumas",
            "HOME_SCORE": "98.96",
            "AWAY_SCORE": "93.92"
        },
        {
            "HOME_TEAM_NAME": "🏉THE💀REBELS🏉",
            "AWAY_TEAM_NAME": "Under the InfluWENTZ", 
            "HOME_SCORE": "132.52",
            "AWAY_SCORE": "120.16"
        }
    ]
    
    print("🏆 TESTING AWARDS CALCULATION")
    print("=" * 50)
    
    # Test the awards calculation function
    from weekly_recap import calculate_weekly_awards_fixed
    
    awards = calculate_weekly_awards_fixed(sample_games)
    
    print("📊 Sample Game Data:")
    for i, game in enumerate(sample_games, 1):
        home_score = game["HOME_SCORE"]
        away_score = game["AWAY_SCORE"]
        print(f"  Game {i}: {game['HOME_TEAM_NAME']} ({home_score}) vs {game['AWAY_TEAM_NAME']} ({away_score})")
    
    print(f"\n🏆 CALCULATED AWARDS:")
    print(f"  Top Score: {awards['top_score']['team']} ({awards['top_score']['points']})")
    print(f"  Cupcake (Low): {awards['low_score']['team']} ({awards['low_score']['points']})")
    print(f"  Kitty (Gap): {awards['largest_gap']['desc']} (gap: {awards['largest_gap']['gap']})")
    
    # Validate results
    print(f"\n✅ VALIDATION:")
    
    # Expected results based on sample data
    expected_top = "Jimmy Birds"  # 132.82
    expected_low = "Avondale Welders"  # 82.1
    expected_gap = 132.82 - 82.1  # 50.72
    
    if awards['top_score']['team'] == expected_top:
        print(f"  ✅ Top Score correct: {expected_top}")
    else:
        print(f"  ❌ Top Score wrong: got {awards['top_score']['team']}, expected {expected_top}")
    
    if awards['low_score']['team'] == expected_low:
        print(f"  ✅ Cupcake correct: {expected_low}")
    else:
        print(f"  ❌ Cupcake wrong: got {awards['low_score']['team']}, expected {expected_low}")
    
    gap_value = float(awards['largest_gap']['gap'])
    if abs(gap_value - expected_gap) < 0.1:
        print(f"  ✅ Gap calculation correct: {gap_value:.1f}")
    else:
        print(f"  ❌ Gap wrong: got {gap_value:.1f}, expected {expected_gap:.1f}")
    
    return awards

def test_template_context_mapping():
    """Test that awards map correctly to template variables"""
    
    print(f"\n📝 TESTING TEMPLATE CONTEXT MAPPING")
    print("=" * 50)
    
    # Test the mapping logic from the build function
    sample_awards = {
        "top_score": {"team": "Jimmy Birds", "points": "132.8"},
        "low_score": {"team": "Avondale Welders", "points": "82.1"},
        "largest_gap": {"desc": "Jimmy Birds vs Avondale Welders", "gap": "50.7"}
    }
    
    # Map to template variables (same logic as in build_weekly_recap)
    template_vars = {
        "AWARD_TOP_TEAM": sample_awards["top_score"].get("team", ""),
        "AWARD_TOP_NOTE": sample_awards["top_score"].get("points", ""),
        "AWARD_CUPCAKE_TEAM": sample_awards["low_score"].get("team", ""),
        "AWARD_CUPCAKE_NOTE": sample_awards["low_score"].get("points", ""),
        "AWARD_KITTY_TEAM": sample_awards["largest_gap"].get("desc", ""),
        "AWARD_KITTY_NOTE": sample_awards["largest_gap"].get("gap", "")
    }
    
    print("📋 Template Variable Mapping:")
    for var, value in template_vars.items():
        status = "✅" if value else "❌"
        print(f"  {status} {var}: '{value}'")
    
    # Check what your Word template expects
    print(f"\n📄 Your Word template should have these placeholders:")
    print(f"  {{{{ AWARD_TOP_TEAM }}}} ({{{{ AWARD_TOP_NOTE }}}}) - for Top Score")
    print(f"  {{{{ AWARD_CUPCAKE_TEAM }}}} ({{{{ AWARD_CUPCAKE_NOTE }}}}) - for Cupcake Award")  
    print(f"  {{{{ AWARD_KITTY_TEAM }}}} ({{{{ AWARD_KITTY_NOTE }}}}) - for Kitty Award")
    
    return template_vars

def test_with_real_api(league_id, year, week):
    """Test with real ESPN API data"""
    
    print(f"\n🌐 TESTING WITH REAL API DATA")
    print(f"League: {league_id}, Year: {year}, Week: {week}")
    print("=" * 50)
    
    try:
        # Try to get real data
        import gazette_data
        
        ctx = gazette_data.assemble_context(str(league_id), year, week)
        games = ctx.get("GAMES", [])
        
        if not games:
            print("❌ No games data from API")
            return
        
        print(f"📊 Found {len(games)} games from API:")
        for i, game in enumerate(games, 1):
            home_team = game.get("HOME_TEAM_NAME", "Unknown")
            away_team = game.get("AWAY_TEAM_NAME", "Unknown")
            home_score = game.get("HOME_SCORE", "N/A")
            away_score = game.get("AWAY_SCORE", "N/A")
            print(f"  Game {i}: {home_team} ({home_score}) vs {away_team} ({away_score})")
        
        # Test awards calculation with real data
        from weekly_recap import calculate_weekly_awards_fixed
        awards = calculate_weekly_awards_fixed(games)
        
        print(f"\n🏆 REAL DATA AWARDS:")
        print(f"  Top Score: {awards['top_score']['team']} ({awards['top_score']['points']})")
        print(f"  Cupcake: {awards['low_score']['team']} ({awards['low_score']['points']})")
        print(f"  Kitty Gap: {awards['largest_gap']['desc']} ({awards['largest_gap']['gap']})")
        
    except Exception as e:
        print(f"❌ Real API test failed: {e}")

if __name__ == "__main__":
    # Test with sample data first
    test_awards_with_sample_data()
    
    # Test template mapping
    test_template_context_mapping()
    
    # Test with real data if league ID provided
    if len(sys.argv) >= 4:
        league_id = sys.argv[1]
        year = int(sys.argv[2])
        week = int(sys.argv[3])
        test_with_real_api(league_id, year, week)
    else:
        print(f"\n💡 To test with real data, run:")
        print(f"   python test_awards.py YOUR_LEAGUE_ID 2024 5")
    
    print(f"\n🎯 If sample tests pass but your document shows empty awards,")
    print(f"   the issue is likely in your Word template placeholders.")
    print(f"   Make sure your template uses {{ AWARD_TOP_TEAM }} etc.")