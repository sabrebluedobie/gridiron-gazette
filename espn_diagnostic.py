#!/usr/bin/env python3
"""
ESPN API Diagnostic - Run this to see exactly what your ESPN API returns
"""

import os
import json
from pathlib import Path

def main():
    print("🔍 ESPN API Diagnostic Tool\n")
    
    # Load config
    try:
        with open('leagues.json') as f:
            config = json.load(f)[0]
        print(f"League: {config.get('name')}")
        print(f"League ID: {config['league_id']}")
        print(f"Year: {config['year']}")
    except Exception as e:
        print(f"❌ Error loading leagues.json: {e}")
        return
    
    # Get credentials
    espn_s2 = os.getenv('ESPN_S2')
    swid = os.getenv('SWID')
    
    if not espn_s2 or not swid:
        print("❌ Missing ESPN_S2 or SWID environment variables")
        print("Set them in your .env file or environment")
        return
    
    print(f"ESPN_S2: {espn_s2[:10]}...{espn_s2[-10:]}")
    print(f"SWID: {swid}")
    print()
    
    try:
        from espn_api.football import League
        
        print("Connecting to ESPN...")
        league = League(
            league_id=config['league_id'],
            year=config['year'],
            espn_s2=espn_s2,
            swid=swid
        )
        
        print(f"✅ Connected to: {league.settings.name}")
        print(f"Current week: {getattr(league, 'current_week', 'Unknown')}")
        print(f"Number of teams: {len(league.teams)}")
        print()
        
        # Analyze teams
        print("=== TEAM ANALYSIS ===")
        for i, team in enumerate(league.teams, 1):
            print(f"\n--- Team {i} ---")
            print(f"Raw type: {type(team)}")
            
            # Show all non-private attributes
            attrs = [attr for attr in dir(team) if not attr.startswith('_')]
            print(f"Available attributes: {attrs[:10]}...")  # Show first 10
            
            # Try to get basic info safely
            team_name = "Unknown"
            owner_name = "Unknown"
            
            # Team name
            for name_attr in ['team_name', 'name', 'teamName']:
                try:
                    if hasattr(team, name_attr):
                        team_name = getattr(team, name_attr) or "Unknown"
                        break
                except:
                    continue
            
            # Owner name - this is where it might be failing
            print("Trying to get owner...")
            for owner_attr in ['owner', 'owner_name', 'ownerName', 'manager']:
                try:
                    if hasattr(team, owner_attr):
                        owner_obj = getattr(team, owner_attr)
                        print(f"  {owner_attr}: {type(owner_obj)} = {owner_obj}")
                        
                        if owner_obj is None:
                            print(f"  {owner_attr} is None")
                            continue
                        
                        # If it's a string, use it directly
                        if isinstance(owner_obj, str):
                            owner_name = owner_obj
                            break
                        
                        # If it's an object, try to get name from it
                        if hasattr(owner_obj, 'name'):
                            owner_name = owner_obj.name
                            break
                        elif hasattr(owner_obj, 'display_name'):
                            owner_name = owner_obj.display_name
                            break
                        else:
                            owner_name = str(owner_obj)
                            break
                            
                except Exception as e:
                    print(f"  ❌ Error accessing {owner_attr}: {e}")
                    continue
            
            print(f"Team Name: {team_name}")
            print(f"Owner: {owner_name}")
            
            # Try to get record
            try:
                wins = getattr(team, 'wins', '?')
                losses = getattr(team, 'losses', '?')
                print(f"Record: {wins}-{losses}")
            except:
                print("Record: Unknown")
        
        # Test getting scoreboard
        print(f"\n=== SCOREBOARD TEST (Week 1) ===")
        try:
            scoreboard = league.scoreboard(week=1)
            print(f"Found {len(scoreboard)} games")
            
            for i, game in enumerate(scoreboard, 1):
                print(f"\n--- Game {i} ---")
                print(f"Game type: {type(game)}")
                
                try:
                    home = getattr(game, 'home_team', None)
                    away = getattr(game, 'away_team', None)
                    
                    if home:
                        home_name = getattr(home, 'team_name', 'Unknown Home')
                        print(f"Home: {home_name}")
                    else:
                        print("Home: None")
                    
                    if away:
                        away_name = getattr(away, 'team_name', 'Unknown Away')
                        print(f"Away: {away_name}")
                    else:
                        print("Away: None")
                    
                    # Try to get scores
                    home_score = getattr(game, 'home_score', 'No score')
                    away_score = getattr(game, 'away_score', 'No score')
                    print(f"Score: {home_score} - {away_score}")
                    
                except Exception as e:
                    print(f"Error processing game: {e}")
                
                if i >= 3:  # Only show first 3 games
                    print("... (showing first 3 games only)")
                    break
                    
        except Exception as e:
            print(f"❌ Error getting scoreboard: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"\n✅ Diagnostic complete!")
        print(f"If you see errors above, that's what's causing your build to fail.")
        
    except Exception as e:
        print(f"❌ Failed to connect to ESPN: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()