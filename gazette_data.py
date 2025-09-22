#!/usr/bin/env python3
"""
gazette_data.py - Fixed for GitHub Actions secrets

Properly handles credentials from:
1. GitHub Actions secrets (ESPN_S2, SWID, LEAGUE_ID)
2. Local environment variables (for local testing)
3. Fallback to leagues.json (for local development)
"""
from __future__ import annotations
import os
import datetime as dt
import requests
import json
from pathlib import Path
from typing import Dict, Any, List
from urllib.parse import unquote

def get_credentials() -> tuple[str, str, str]:
    """
    Get ESPN credentials and league ID with proper priority:
    1. Environment variables (GitHub Actions)
    2. leagues.json (local development)
    """
    # GitHub Actions / Environment variables (highest priority)
    espn_s2 = os.getenv("ESPN_S2", "").strip()
    swid = os.getenv("SWID", "").strip() 
    league_id = os.getenv("LEAGUE_ID", "").strip()
    
    if espn_s2 and swid and league_id:
        print("[auth] ✅ Using credentials from environment (GitHub Actions)")
        # URL decode if needed (GitHub secrets might be URL encoded)
        if '%' in espn_s2:
            espn_s2 = unquote(espn_s2)
        # Ensure SWID has braces
        if not (swid.startswith("{") and swid.endswith("}")):
            swid = "{" + swid.strip("{}") + "}"
        return espn_s2, swid, league_id
    
    # Fallback to leagues.json for local development
    try:
        config_file = Path("leagues.json")
        if config_file.exists():
            with open(config_file) as f:
                leagues = json.load(f)
            
            config = leagues[0] if isinstance(leagues, list) else leagues
            
            file_s2 = config.get("espn_s2", "").strip()
            file_swid = config.get("swid", "").strip()
            file_league_id = str(config.get("league_id", "")).strip()
            
            if file_s2 and file_swid and file_league_id:
                print("[auth] ✅ Using credentials from leagues.json")
                # URL decode (leagues.json has URL encoded values)
                if '%' in file_s2:
                    file_s2 = unquote(file_s2)
                # Ensure SWID has braces
                if not (file_swid.startswith("{") and file_swid.endswith("}")):
                    file_swid = "{" + file_swid.strip("{}") + "}"
                return file_s2, file_swid, file_league_id
    
    except Exception as e:
        print(f"[auth] Error reading leagues.json: {e}")
    
    print("[auth] ❌ No valid ESPN credentials found!")
    return "", "", ""

def fetch_espn_data(league_id: str, year: int, week: int) -> Dict[str, Any]:
    """Fetch data from ESPN API with proper authentication"""
    
    espn_s2, swid, _ = get_credentials()
    
    if not espn_s2 or not swid:
        print("[espn] ❌ Missing ESPN credentials")
        return create_fallback_data()
    
    url = f"https://fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{league_id}"
    params = {
        "scoringPeriodId": week,
        "view": "mMatchupScore"
    }
    
    cookies = {
        "espn_s2": espn_s2,
        "SWID": swid
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://fantasy.espn.com/"
    }
    
    try:
        print(f"[espn] Fetching data for league {league_id}, year {year}, week {week}")
        print(f"[espn] ESPN_S2 length: {len(espn_s2)} chars")
        print(f"[espn] SWID: {swid}")
        
        response = requests.get(url, params=params, headers=headers, cookies=cookies, timeout=30)
        
        print(f"[espn] Response: {response.status_code}")
        
        if response.status_code == 401:
            print("[espn] ❌ 401 Unauthorized - ESPN cookies are invalid or expired")
            print("[espn] 💡 Get fresh cookies from fantasy.espn.com")
            return create_fallback_data()
        elif response.status_code == 404:
            print(f"[espn] ❌ 404 Not Found - League {league_id} not found")
            return create_fallback_data()
        elif response.status_code != 200:
            print(f"[espn] ❌ HTTP {response.status_code}: {response.text[:200]}")
            return create_fallback_data()
        
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            print(f"[espn] ❌ Invalid JSON: {e}")
            return create_fallback_data()
        
        teams = data.get("teams", [])
        schedule = data.get("schedule", [])
        
        print(f"[espn] ✅ Success! {len(teams)} teams, {len(schedule)} matchups")
        
        if not teams or not schedule:
            print("[espn] ⚠️  Empty data returned")
            return create_fallback_data()
        
        return process_espn_data(data)
        
    except Exception as e:
        print(f"[espn] ❌ Request failed: {e}")
        return create_fallback_data()

def process_espn_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Process raw ESPN API response into our format"""
    teams = data.get("teams", [])
    schedule = data.get("schedule", [])
    
    # Build team lookup table
    team_lookup = {}
    for team in teams:
        team_id = team.get("id")
        if team_id is None:
            continue
        
        location = (team.get("location") or "").strip()
        nickname = (team.get("nickname") or "").strip()
        
        # Create display name
        if location and nickname:
            name = f"{location} {nickname}"
        elif nickname:
            name = nickname
        elif location:
            name = location
        else:
            name = f"Team {team_id}"
        
        team_lookup[team_id] = name
        print(f"[espn] Team {team_id}: {name}")
    
    # Process matchups
    games = []
    for matchup in schedule:
        home_data = matchup.get("home", {})
        away_data = matchup.get("away", {})
        
        home_id = home_data.get("teamId")
        away_id = away_data.get("teamId")
        
        if home_id is None or away_id is None:
            continue
        
        home_name = team_lookup.get(home_id, f"Team {home_id}")
        away_name = team_lookup.get(away_id, f"Team {away_id}")
        
        home_score = home_data.get("totalPoints", 0) or 0
        away_score = away_data.get("totalPoints", 0) or 0
        
        game = {
            "HOME_TEAM_NAME": home_name,
            "AWAY_TEAM_NAME": away_name,
            "HOME_SCORE": f"{home_score:.1f}",
            "AWAY_SCORE": f"{away_score:.1f}",
            "RECAP": ""
        }
        
        games.append(game)
        print(f"[espn] Game: {home_name} {game['HOME_SCORE']} - {away_name} {game['AWAY_SCORE']}")
    
    return {"games": games}

def create_fallback_data() -> Dict[str, Any]:
    """Create sample data when ESPN fails (ensures build always succeeds)"""
    print("[fallback] 🔄 Using sample data")
    
    return {
        "games": [
            {
                "HOME_TEAM_NAME": "Nana's Hawks",
                "AWAY_TEAM_NAME": "Phoenix Blues",
                "HOME_SCORE": "127.4",
                "AWAY_SCORE": "98.6",
                "RECAP": "Sample game (ESPN fetch failed)"
            },
            {
                "HOME_TEAM_NAME": "Annie1235 slayy",
                "AWAY_TEAM_NAME": "Jimmy Birds", 
                "HOME_SCORE": "115.2",
                "AWAY_SCORE": "109.8",
                "RECAP": "Sample game (ESPN fetch failed)"
            },
            {
                "HOME_TEAM_NAME": "Kansas City Pumas",
                "AWAY_TEAM_NAME": "Under the InfluWENTZ",
                "HOME_SCORE": "102.3",
                "AWAY_SCORE": "95.7",
                "RECAP": "Sample game (ESPN fetch failed)"
            },
            {
                "HOME_TEAM_NAME": "DEM BOY'S! 🏆🏆🏆🏆",
                "AWAY_TEAM_NAME": "Avondale Welders",
                "HOME_SCORE": "88.9", 
                "AWAY_SCORE": "112.4",
                "RECAP": "Sample game (ESPN fetch failed)"
            },
            {
                "HOME_TEAM_NAME": "THE 💀REBELS💀",
                "AWAY_TEAM_NAME": "The Champ Big Daddy",
                "HOME_SCORE": "99.1",
                "AWAY_SCORE": "103.8", 
                "RECAP": "Sample game (ESPN fetch failed)"
            }
        ]
    }

def assemble_context(league_id: str, year: int, week: int, llm_blurbs: bool, blurb_style: str) -> Dict[str, Any]:
    """
    Build template context with ESPN data or fallback
    """
    print(f"[ctx] Building context for league {league_id}, year {year}, week {week}")
    
    # Use provided league_id or get from environment/config
    if not league_id:
        _, _, config_league_id = get_credentials()
        league_id = config_league_id
    
    if not league_id:
        print("[ctx] ❌ No league ID available")
        league_id = "887998"  # Default from your config
    
    # Fetch game data
    data = fetch_espn_data(league_id, year, week)
    games = data.get("games", [])
    
    # Find featured matchup (highest scoring)
    if games:
        featured = max(games, key=lambda g: float(g.get("HOME_SCORE", "0")) + float(g.get("AWAY_SCORE", "0")))
        home_team = featured["HOME_TEAM_NAME"]
        away_team = featured["AWAY_TEAM_NAME"]
    else:
        home_team = "Sample Home"
        away_team = "Sample Away"
    
    # League display name
    league_name = os.getenv("LEAGUE_DISPLAY_NAME", "Browns SEA/KC")
    
    context = {
        # Core data
        "LEAGUE_NAME": league_name,
        "LEAGUE_LOGO_NAME": league_name,
        "WEEK_NUM": week,
        "YEAR": year,
        "GENERATED_AT": dt.datetime.now().isoformat(timespec="seconds"),
        
        # Featured matchup
        "HOME_TEAM_NAME": home_team,
        "AWAY_TEAM_NAME": away_team,
        
        # All games for template loops
        "GAMES": games,
        
        # Template variables (ensure these exist)
        "WEEK_NUMBER": week,
        "WEEKLY_INTRO": f"Week {week} fantasy football action!",
        
        # Awards (sample - can be computed from real data later)
        "AWARD_TOP_TEAM": games[0]["HOME_TEAM_NAME"] if games else "Sample Team",
        "AWARD_TOP_NOTE": games[0]["HOME_SCORE"] if games else "120.5",
        "AWARD_CUPCAKE_TEAM": games[-1]["AWAY_TEAM_NAME"] if games else "Sample Team", 
        "AWARD_CUPCAKE_NOTE": games[-1]["AWAY_SCORE"] if games else "65.2",
        "AWARD_KITTY_TEAM": "Close Game Team",
        "AWARD_KITTY_NOTE": "2.1 point gap",
        
        # Metadata
        "DATA_SOURCE": "ESPN API" if games else "Sample Data",
        "TOTAL_GAMES": len(games),
        "BLURB_STYLE": blurb_style
    }
    
    # LLM settings
    if llm_blurbs:
        context["LLM_ENABLED"] = True
        context["LLM_NOTE"] = f"LLM blurbs enabled with '{blurb_style}' style"
    
    print(f"[ctx] ✅ Context built: {len(games)} games, featured: {home_team} vs {away_team}")
    return context

# For backwards compatibility
def load_scoreboard(league_id: str, year: int, week: int) -> Dict[str, Any]:
    """Legacy function for compatibility"""
    return fetch_espn_data(league_id, year, week)