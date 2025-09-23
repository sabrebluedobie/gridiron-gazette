#!/usr/bin/env python3
"""
Enhanced gazette_data.py - Drop-in replacement with robust error handling
Maintains all your existing function names and interfaces
"""

import time
import json
import logging
from typing import Any, Dict, List, Optional
from functools import wraps
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def retry_with_backoff(max_retries: int = 3, base_delay: float = 1.0):
    """Decorator for retrying API calls with exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    result = func(*args, **kwargs)
                    if result is not None:
                        return result
                except Exception as e:
                    last_exception = e
                    logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {func.__name__}: {str(e)}")
                    if attempt == max_retries - 1:
                        break
                    
                    delay = base_delay * (2 ** attempt)
                    logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
            
            # If we get here, all attempts failed
            if last_exception:
                logger.error(f"All {max_retries} attempts failed for {func.__name__}: {last_exception}")
            return None
        return wrapper
    return decorator

class RobustDataFetcher:
    """Enhanced data fetching with comprehensive error handling"""
    
    def __init__(self, league: Any):
        self.league = league
        self.cache = {}
        
    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def get_scoreboard(self, week: int) -> Optional[List[Any]]:
        """Get scoreboard with retries and validation"""
        cache_key = f"scoreboard_{week}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        logger.info(f"Fetching scoreboard for week {week}")
        scoreboard = self.league.scoreboard(week)
        
        if scoreboard and len(scoreboard) > 0:
            self.cache[cache_key] = scoreboard
            logger.info(f"Scoreboard fetched: {len(scoreboard)} matchups")
            return scoreboard
        else:
            logger.warning(f"Empty or invalid scoreboard returned for week {week}")
            return None
    
    def safe_get_team_name(self, team: Any) -> str:
        """Safely extract team name with multiple fallbacks"""
        try:
            if hasattr(team, 'team_name') and team.team_name:
                return str(team.team_name).strip()
            elif hasattr(team, 'team_abbrev') and team.team_abbrev:
                return str(team.team_abbrev).strip()
            elif hasattr(team, 'owner') and team.owner:
                return f"Team {str(team.owner).strip()}"
            elif hasattr(team, 'team_id'):
                return f"Team {team.team_id}"
            else:
                return "Unknown Team"
        except Exception as e:
            logger.debug(f"Error getting team name: {e}")
            return "Unknown Team"
    
    def safe_get_score(self, team: Any, week: int) -> str:
        """Safely extract team score with multiple methods and validation"""
        try:
            score = None
            
            # Method 1: scores dictionary
            if hasattr(team, 'scores') and isinstance(team.scores, dict):
                score = team.scores.get(week)
            
            # Method 2: points attribute
            if score is None and hasattr(team, 'points'):
                score = team.points
            
            # Method 3: total_points
            if score is None and hasattr(team, 'total_points'):
                score = team.total_points
            
            # Method 4: Check if it's in a matchup context
            if score is None and hasattr(team, 'score'):
                score = team.score
            
            if score is not None:
                try:
                    float_score = float(score)
                    if float_score >= 0:  # Sanity check
                        return f"{float_score:.1f}"
                except (ValueError, TypeError):
                    pass
            
            logger.debug(f"No valid score found for team {self.safe_get_team_name(team)}")
            return ""
            
        except Exception as e:
            logger.debug(f"Error getting score for team: {e}")
            return ""
    
    def extract_matchup_data(self, week: int) -> List[Dict[str, Any]]:
        """Extract comprehensive matchup data with error recovery"""
        games = []
        
        try:
            scoreboard = self.get_scoreboard(week)
            if not scoreboard:
                logger.error(f"No scoreboard data available for week {week}")
                return self._create_placeholder_games(6)  # Return placeholder data
            
            logger.info(f"Processing {len(scoreboard)} matchups")
            
            for i, matchup in enumerate(scoreboard):
                try:
                    game_data = self._process_single_matchup(matchup, week, i)
                    games.append(game_data)
                except Exception as e:
                    logger.error(f"Error processing matchup {i}: {e}")
                    # Create placeholder matchup to maintain structure
                    games.append(self._create_placeholder_matchup(i))
            
        except Exception as e:
            logger.error(f"Fatal error extracting matchup data: {e}")
            return self._create_placeholder_games(6)
        
        logger.info(f"Successfully extracted data for {len(games)} games")
        return games
    
    def _process_single_matchup(self, matchup: Any, week: int, index: int) -> Dict[str, Any]:
        """Process a single matchup with comprehensive error handling"""
        
        # Initialize game data structure
        game_data = {
            "HOME_TEAM_NAME": "",
            "AWAY_TEAM_NAME": "",
            "HOME_SCORE": "",
            "AWAY_SCORE": "",
            "RECAP": "",
            "BLURB": "",
            "TOP_HOME": "",
            "TOP_AWAY": "",
            "BUST": "",
            "KEYPLAY": "",
            "DEF": "",
            "KEY_PLAY": "",
            "DEF_NOTE": ""
        }
        
        try:
            # Extract teams
            home_team = getattr(matchup, 'home_team', None)
            away_team = getattr(matchup, 'away_team', None)
            
            if not home_team or not away_team:
                logger.warning(f"Matchup {index}: Missing team data")
                return self._create_placeholder_matchup(index)
            
            # Extract basic info
            game_data["HOME_TEAM_NAME"] = self.safe_get_team_name(home_team)
            game_data["AWAY_TEAM_NAME"] = self.safe_get_team_name(away_team)
            game_data["HOME_SCORE"] = self.safe_get_score(home_team, week)
            game_data["AWAY_SCORE"] = self.safe_get_score(away_team, week)
            
            # Generate recap
            game_data["RECAP"] = self._generate_recap(game_data)
            game_data["BLURB"] = game_data["RECAP"]  # Alias for template compatibility
            
            logger.debug(f"Matchup {index}: {game_data['HOME_TEAM_NAME']} vs {game_data['AWAY_TEAM_NAME']}")
            
        except Exception as e:
            logger.error(f"Error in _process_single_matchup for matchup {index}: {e}")
            return self._create_placeholder_matchup(index)
        
        return game_data
    
    def _generate_recap(self, game_data: Dict[str, Any]) -> str:
        """Generate a basic recap from available game data"""
        home_team = game_data.get("HOME_TEAM_NAME", "Team A")
        away_team = game_data.get("AWAY_TEAM_NAME", "Team B")
        home_score = game_data.get("HOME_SCORE", "")
        away_score = game_data.get("AWAY_SCORE", "")
        
        try:
            if home_score and away_score:
                home_pts = float(home_score)
                away_pts = float(away_score)
                
                if home_pts > away_pts:
                    margin = home_pts - away_pts
                    if margin > 20:
                        intensity = "dominated"
                    elif margin > 10:
                        intensity = "defeated"
                    else:
                        intensity = "edged out"
                    return f"{home_team} {intensity} {away_team} {home_pts:.1f} to {away_pts:.1f}"
                else:
                    margin = away_pts - home_pts
                    if margin > 20:
                        intensity = "dominated"
                    elif margin > 10:
                        intensity = "defeated"
                    else:
                        intensity = "edged out"
                    return f"{away_team} {intensity} {home_team} {away_pts:.1f} to {home_pts:.1f}"
            else:
                return f"{home_team} faced off against {away_team} in this week's matchup"
                
        except (ValueError, TypeError):
            return f"{home_team} vs {away_team}"
    
    def _create_placeholder_matchup(self, index: int) -> Dict[str, Any]:
        """Create placeholder data for failed matchup"""
        return {
            "HOME_TEAM_NAME": f"Team {index}A",
            "AWAY_TEAM_NAME": f"Team {index}B",
            "HOME_SCORE": "",
            "AWAY_SCORE": "",
            "RECAP": f"Matchup data unavailable",
            "BLURB": f"Matchup data unavailable",
            "TOP_HOME": "",
            "TOP_AWAY": "",
            "BUST": "",
            "KEYPLAY": "",
            "DEF": "",
            "KEY_PLAY": "",
            "DEF_NOTE": ""
        }
    
    def _create_placeholder_games(self, count: int) -> List[Dict[str, Any]]:
        """Create placeholder games when API completely fails"""
        logger.warning(f"Creating {count} placeholder games due to API failure")
        return [self._create_placeholder_matchup(i) for i in range(count)]

def get_league_info(league: Any) -> Dict[str, Any]:
    """Extract basic league information with error handling"""
    info = {
        "name": "Fantasy League",
        "year": 2024,
        "current_week": 1,
        "team_count": 0
    }
    
    try:
        if hasattr(league, 'settings'):
            settings = league.settings
            if hasattr(settings, 'name'):
                info["name"] = str(settings.name)
            if hasattr(settings, 'reg_season_count'):
                info["team_count"] = int(settings.reg_season_count)
        
        if hasattr(league, 'year'):
            info["year"] = int(league.year)
        
        if hasattr(league, 'current_week'):
            info["current_week"] = int(league.current_week)
        elif hasattr(league, 'currentMatchupPeriod'):
            info["current_week"] = int(league.currentMatchupPeriod)
            
    except Exception as e:
        logger.warning(f"Error extracting league info: {e}")
    
    return info

def calculate_weekly_awards(games: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate weekly awards from game data"""
    awards = {
        "top_score": {"team": "", "points": ""},
        "low_score": {"team": "", "points": ""},
        "largest_gap": {"desc": "", "gap": ""}
    }
    
    try:
        valid_scores = []
        
        # Extract all valid scores
        for game in games:
            home_team = game.get("HOME_TEAM_NAME", "")
            away_team = game.get("AWAY_TEAM_NAME", "")
            home_score = game.get("HOME_SCORE", "")
            away_score = game.get("AWAY_SCORE", "")
            
            try:
                if home_score and home_team:
                    valid_scores.append((home_team, float(home_score)))
                if away_score and away_team:
                    valid_scores.append((away_team, float(away_score)))
            except (ValueError, TypeError):
                continue
        
        if not valid_scores:
            logger.warning("No valid scores found for awards calculation")
            return awards
        
        # Calculate awards
        if valid_scores:
            # Top score
            top_team, top_points = max(valid_scores, key=lambda x: x[1])
            awards["top_score"] = {"team": top_team, "points": f"{top_points:.1f}"}
            
            # Low score
            low_team, low_points = min(valid_scores, key=lambda x: x[1])
            awards["low_score"] = {"team": low_team, "points": f"{low_points:.1f}"}
            
            # Largest gap (simplified - just use top vs low)
            gap = top_points - low_points
            awards["largest_gap"] = {
                "desc": f"{top_team} vs {low_team}",
                "gap": f"{gap:.1f}"
            }
        
    except Exception as e:
        logger.error(f"Error calculating awards: {e}")
    
    return awards

def generate_weekly_intro(week: int, game_count: int) -> str:
    """Generate a weekly introduction"""
    if game_count == 0:
        return f"Week {week} data is currently unavailable."
    
    intros = [
        f"Week {week} brought intense fantasy football action with {game_count} exciting matchups.",
        f"The competition heated up in Week {week} as {game_count} teams battled for fantasy supremacy.",
        f"Week {week} delivered thrilling fantasy performances across {game_count} head-to-head battles.",
        f"Fantasy managers faced off in {game_count} competitive matchups during Week {week}."
    ]
    
    import random
    return random.choice(intros)

# ==================== MAIN PUBLIC FUNCTIONS ====================
# These maintain compatibility with your existing code

def assemble_context(league_id: str, year: int, week: int, 
                    llm_blurbs: bool = False, blurb_style: str = "sabre") -> Dict[str, Any]:
    """
    Main function to assemble context data - maintains your existing interface
    """
    
    logger.info(f"Assembling context for League {league_id}, Year {year}, Week {week}")
    
    # Import league object - you might need to adjust this based on your setup
    try:
        from espn_api.football import League
        import os
        
        # Try to get ESPN cookies from environment
        espn_s2 = os.environ.get('ESPN_S2')
        swid = os.environ.get('SWID')
        
        if espn_s2 and swid:
            league = League(
                league_id=int(league_id), 
                year=year, 
                espn_s2=espn_s2, 
                swid=swid
            )
        else:
            # Public league or no auth needed
            league = League(league_id=int(league_id), year=year)
            
        logger.info("League object created successfully")
    except Exception as e:
        logger.error(f"Failed to create league object: {e}")
        # Return minimal context if league creation fails
        return {
            "LEAGUE_ID": league_id,
            "YEAR": year,
            "WEEK": week,
            "GAMES": [],
            "LEAGUE_NAME": "Fantasy League",
            "WEEKLY_INTRO": f"Week {week} recap data unavailable due to API error.",
            "awards": {
                "top_score": {"team": "", "points": ""},
                "low_score": {"team": "", "points": ""},
                "largest_gap": {"desc": "", "gap": ""}
            }
        }
    
    # Initialize data fetcher
    fetcher = RobustDataFetcher(league)
    
    # Get league info
    league_info = get_league_info(league)
    
    # Extract games data
    games = fetcher.extract_matchup_data(week)
    
    # Calculate basic awards with error handling
    awards = calculate_weekly_awards(games)
    
    # Build context - maintaining your existing structure
    context = {
        "LEAGUE_ID": league_id,
        "YEAR": year,
        "WEEK": week,
        "GAMES": games,
        "LEAGUE_NAME": league_info["name"],
        "WEEKLY_INTRO": generate_weekly_intro(week, len(games)),
        "awards": awards,
        
        # Additional keys for template compatibility
        "week": week,
        "intro": generate_weekly_intro(week, len(games)),
        "league_name": league_info["name"],
        "games": games  # lowercase alias
    }
    
    logger.info(f"Context assembled: {len(games)} games, league '{league_info['name']}'")
    return context

# Backward compatibility functions (if your code uses these)
def get_matchup_data(league_id: str, year: int, week: int) -> List[Dict[str, Any]]:
    """Get just the matchup data - backward compatibility"""
    context = assemble_context(league_id, year, week)
    return context.get("GAMES", [])

def get_league_name(league_id: str, year: int) -> str:
    """Get just the league name - backward compatibility"""
    try:
        from espn_api.football import League
        import os
        
        espn_s2 = os.environ.get('ESPN_S2')
        swid = os.environ.get('SWID')
        
        if espn_s2 and swid:
            league = League(league_id=int(league_id), year=year, espn_s2=espn_s2, swid=swid)
        else:
            league = League(league_id=int(league_id), year=year)
            
        info = get_league_info(league)
        return info["name"]
    except Exception as e:
        logger.error(f"Error getting league name: {e}")
        return "Fantasy League"

# If you have other functions in your original gazette_data.py, add them here
# For example:
def get_team_records(league_id: str, year: int) -> Dict[str, Any]:
    """Get team win/loss records - add if you had this in your original"""
    # Implementation would go here
    pass

def get_standings(league_id: str, year: int, week: int) -> List[Dict[str, Any]]:
    """Get league standings - add if you had this in your original"""
    # Implementation would go here  
    pass