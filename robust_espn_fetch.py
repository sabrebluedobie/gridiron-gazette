#!/usr/bin/env python3
"""
robust_espn_fetch.py - More reliable ESPN API data fetching with retries and validation
"""

import time
import json
from typing import Any, Dict, List, Optional, Tuple
from functools import wraps
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def retry_with_backoff(max_retries: int = 3, base_delay: float = 1.0):
    """Decorator for retrying API calls with exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    result = func(*args, **kwargs)
                    if result is not None:  # Consider None as failure
                        return result
                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {str(e)}")
                    if attempt == max_retries - 1:
                        raise
                    
                delay = base_delay * (2 ** attempt)
                logger.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            
            return None
        return wrapper
    return decorator

class RobustESPNFetcher:
    """Enhanced ESPN data fetcher with error handling and validation"""
    
    def __init__(self, league: Any):
        self.league = league
        self.cache = {}
        
    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def get_scoreboard(self, week: int) -> Optional[List[Any]]:
        """Get scoreboard with retries and validation"""
        cache_key = f"scoreboard_{week}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            scoreboard = self.league.scoreboard(week)
            if scoreboard and len(scoreboard) > 0:
                self.cache[cache_key] = scoreboard
                return scoreboard
            else:
                logger.warning(f"Empty scoreboard returned for week {week}")
                return None
        except Exception as e:
            logger.error(f"Failed to fetch scoreboard for week {week}: {str(e)}")
            raise
    
    @retry_with_backoff(max_retries=2, base_delay=0.5)
    def get_team_lineup(self, team: Any, week: int) -> List[Any]:
        """Get team lineup with fallback methods"""
        try:
            # Method 1: Direct lineup access
            if hasattr(team, 'lineup') and team.lineup:
                return team.lineup
            
            # Method 2: Try roster instead
            if hasattr(team, 'roster') and team.roster:
                logger.info(f"Using roster instead of lineup for {getattr(team, 'team_name', 'unknown')}")
                return team.roster
                
            logger.warning(f"No lineup/roster found for team {getattr(team, 'team_name', 'unknown')}")
            return []
            
        except Exception as e:
            logger.error(f"Failed to get lineup for team: {str(e)}")
            return []
    
    def extract_matchup_data(self, week: int) -> List[Dict[str, Any]]:
        """Extract matchup data with comprehensive error handling"""
        games = []
        
        scoreboard = self.get_scoreboard(week)
        if not scoreboard:
            logger.error(f"No scoreboard data available for week {week}")
            return games
        
        for i, matchup in enumerate(scoreboard):
            try:
                game_data = self._extract_single_matchup(matchup, week, i)
                if game_data:
                    games.append(game_data)
                else:
                    logger.warning(f"Failed to extract data for matchup {i}")
            except Exception as e:
                logger.error(f"Error processing matchup {i}: {str(e)}")
                # Add placeholder data to maintain structure
                games.append({
                    "HOME_TEAM_NAME": f"Team {i}A",
                    "AWAY_TEAM_NAME": f"Team {i}B", 
                    "HOME_SCORE": "",
                    "AWAY_SCORE": "",
                    "RECAP": f"Data unavailable for this matchup (Error: {str(e)})",
                    "TOP_HOME": "",
                    "TOP_AWAY": "",
                    "BUST": "",
                    "KEYPLAY": "",
                    "DEF": ""
                })
        
        return games
    
    def _extract_single_matchup(self, matchup: Any, week: int, matchup_index: int) -> Optional[Dict[str, Any]]:
        """Extract data from a single matchup with multiple fallback strategies"""
        game_data = {}
        
        # Extract team names with fallbacks
        home_team = getattr(matchup, 'home_team', None)
        away_team = getattr(matchup, 'away_team', None)
        
        if not home_team or not away_team:
            logger.warning(f"Missing team data in matchup {matchup_index}")
            return None
        
        game_data["HOME_TEAM_NAME"] = self._safe_get_team_name(home_team)
        game_data["AWAY_TEAM_NAME"] = self._safe_get_team_name(away_team)
        
        # Extract scores with multiple methods
        game_data["HOME_SCORE"] = self._safe_get_score(home_team, week)
        game_data["AWAY_SCORE"] = self._safe_get_score(away_team, week)
        
        # Generate basic recap if scores available
        if game_data["HOME_SCORE"] and game_data["AWAY_SCORE"]:
            try:
                home_score = float(game_data["HOME_SCORE"])
                away_score = float(game_data["AWAY_SCORE"])
                winner = game_data["HOME_TEAM_NAME"] if home_score > away_score else game_data["AWAY_TEAM_NAME"]
                game_data["RECAP"] = f"{winner} wins {max(home_score, away_score):.1f} to {min(home_score, away_score):.1f}"
            except (ValueError, TypeError):
                game_data["RECAP"] = f"{game_data['HOME_TEAM_NAME']} vs {game_data['AWAY_TEAM_NAME']}"
        else:
            game_data["RECAP"] = f"{game_data['HOME_TEAM_NAME']} vs {game_data['AWAY_TEAM_NAME']}"
        
        # Extract player performance data
        home_lineup = self.get_team_lineup(home_team, week)
        away_lineup = self.get_team_lineup(away_team, week)
        
        game_data["TOP_HOME"] = self._get_top_performer(home_lineup)
        game_data["TOP_AWAY"] = self._get_top_performer(away_lineup)
        game_data["BUST"] = self._get_biggest_bust(home_lineup + away_lineup)
        
        # Placeholder for additional data
        game_data["KEYPLAY"] = ""
        game_data["DEF"] = ""
        
        return game_data
    
    def _safe_get_team_name(self, team: Any) -> str:
        """Safely extract team name with fallbacks"""
        if hasattr(team, 'team_name') and team.team_name:
            return str(team.team_name)
        elif hasattr(team, 'team_abbrev') and team.team_abbrev:
            return str(team.team_abbrev)
        elif hasattr(team, 'owner') and team.owner:
            return f"Team {team.owner}"
        else:
            return f"Team {getattr(team, 'team_id', 'Unknown')}"
    
    def _safe_get_score(self, team: Any, week: int) -> str:
        """Safely extract team score with multiple methods"""
        try:
            # Method 1: scores dictionary
            if hasattr(team, 'scores') and isinstance(team.scores, dict):
                score = team.scores.get(week)
                if score is not None:
                    return f"{score:.1f}"
            
            # Method 2: points attribute
            if hasattr(team, 'points') and team.points is not None:
                return f"{team.points:.1f}"
            
            # Method 3: total_points
            if hasattr(team, 'total_points') and team.total_points is not None:
                return f"{team.total_points:.1f}"
                
            return ""
        except Exception as e:
            logger.debug(f"Error getting score: {str(e)}")
            return ""
    
    def _get_top_performer(self, lineup: List[Any]) -> str:
        """Find the top performing player in a lineup"""
        if not lineup:
            return ""
        
        try:
            # Filter to only starters (not bench players)
            starters = [p for p in lineup if self._is_starter(p)]
            if not starters:
                starters = lineup  # Fallback to all players
            
            top_player = max(starters, key=lambda p: self._get_player_points(p))
            points = self._get_player_points(top_player)
            name = getattr(top_player, 'name', 'Unknown Player')
            
            if points > 0:
                return f"{name} ({points:.1f} pts)"
            else:
                return f"{name}"
                
        except Exception as e:
            logger.debug(f"Error getting top performer: {str(e)}")
            return ""
    
    def _get_biggest_bust(self, all_players: List[Any]) -> str:
        """Find the biggest underperformer vs projection"""
        if not all_players:
            return ""
        
        try:
            starters = [p for p in all_players if self._is_starter(p)]
            if not starters:
                return ""
            
            bust_player = None
            worst_diff = 0
            
            for player in starters:
                points = self._get_player_points(player)
                projected = self._get_player_projected_points(player)
                
                if projected > 0:  # Only consider players with projections
                    diff = points - projected
                    if diff < worst_diff:
                        worst_diff = diff
                        bust_player = player
            
            if bust_player:
                name = getattr(bust_player, 'name', 'Unknown')
                points = self._get_player_points(bust_player)
                projected = self._get_player_projected_points(bust_player)
                return f"{name} ({points:.1f} vs {projected:.1f} proj)"
            
            return ""
            
        except Exception as e:
            logger.debug(f"Error getting bust: {str(e)}")
            return ""
    
    def _is_starter(self, player: Any) -> bool:
        """Check if player was in starting lineup"""
        try:
            slot = getattr(player, 'slot_position', None)
            return slot not in ['BE', 'IR'] if slot else True
        except:
            return True  # Default to considering all players as starters
    
    def _get_player_points(self, player: Any) -> float:
        """Safely get player points"""
        try:
            if hasattr(player, 'points') and player.points is not None:
                return float(player.points)
            elif hasattr(player, 'total_points') and player.total_points is not None:
                return float(player.total_points)
            return 0.0
        except (ValueError, TypeError):
            return 0.0
    
    def _get_player_projected_points(self, player: Any) -> float:
        """Safely get player projected points"""
        try:
            if hasattr(player, 'projected_points') and player.projected_points is not None:
                return float(player.projected_points)
            elif hasattr(player, 'projected_total_points') and player.projected_total_points is not None:
                return float(player.projected_total_points)
            return 0.0
        except (ValueError, TypeError):
            return 0.0

# Integration function for your existing code
def robust_assemble_context(league: Any, league_id: str, year: int, week: int, 
                          llm_blurbs: bool = False, blurb_style: str = "sabre") -> Dict[str, Any]:
    """
    Enhanced version of your assemble_context function with robust error handling
    """
    fetcher = RobustESPNFetcher(league)
    
    # Extract games data
    games = fetcher.extract_matchup_data(week)
    
    # Basic context structure
    context = {
        "LEAGUE_ID": league_id,
        "YEAR": year,
        "WEEK": week,
        "GAMES": games,
        "LEAGUE_NAME": getattr(getattr(league, 'settings', {}), 'name', 'Fantasy League')
    }
    
    logger.info(f"Successfully extracted {len(games)} games for week {week}")
    
    return context

# Usage in your existing weekly_recap.py:
# Replace the call to gazette_data.assemble_context with:
# ctx = robust_assemble_context(league, str(league_id), year, week, llm_blurbs=False, blurb_style=blurb_style)