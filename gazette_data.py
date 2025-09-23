#!/usr/bin/env python3
"""
gazette_data.py — Enhanced ESPN fetch & context assembly for Gridiron Gazette

Key improvements:
- Robust error handling for ESPN API
- Better environment variable detection
- Retry logic for network issues
- Comprehensive logging
- Fallback mechanisms when data is unavailable
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import os
import logging
import time

log = logging.getLogger("gazette_data")

# ESPN API with fallback handling
try:
    from espn_api.football import League
    ESPN_API_AVAILABLE = True
except Exception as e:
    League = None
    ESPN_API_AVAILABLE = False
    log.warning(f"ESPN API not available: {e}")


# ------------------- Helper Functions -------------------

def _env(name: str) -> Optional[str]:
    """Get environment variable with whitespace handling"""
    v = os.getenv(name)
    return v.strip() if isinstance(v, str) and v.strip() else None

def _coerce_str(x) -> str:
    """Convert any value to a clean string for docxtpl"""
    try:
        if x is None:
            return ""
        if isinstance(x, float):
            # Clean up float display
            s = f"{x:.2f}".rstrip("0").rstrip(".")
            return s if s else "0"
        return str(x).strip()
    except Exception:
        return str(x) if x is not None else ""

def _float_or_none(x) -> Optional[float]:
    """Safely convert to float"""
    try:
        return float(x)
    except (ValueError, TypeError):
        return None

def _team_display_name(team: Any) -> str:
    """
    Get team display name with multiple fallback strategies
    Handles different ESPN API versions and team object structures
    """
    if not team:
        return "Team"
    
    # Try various team name attributes
    name_attrs = ["team_name", "location", "name", "team_abbrev"]
    for attr in name_attrs:
        if hasattr(team, attr):
            value = getattr(team, attr)
            if isinstance(value, str) and value.strip():
                return value.strip()
    
    # Try owner name as fallback
    try:
        if hasattr(team, "owners") and team.owners:
            owner = team.owners[0]
            if hasattr(owner, "display_name"):
                return owner.display_name
            return str(owner)
        elif hasattr(team, "owner"):
            owner = team.owner
            if hasattr(owner, "display_name"):
                return owner.display_name
            return str(owner)
    except Exception:
        pass
    
    return "Team"


# ------------------- League Creation -------------------

def _make_league(league_id: int, year: int) -> Optional[Any]:
    """
    Create ESPN League object with comprehensive error handling
    Supports multiple environment variable naming conventions
    """
    if not ESPN_API_AVAILABLE:
        log.error("ESPN API not available. Install with: pip install espn-api")
        return None
    
    # Try multiple environment variable names for flexibility
    s2_vars = ["ESPN_S2", "S2", "espn_s2"]
    swid_vars = ["SWID", "ESPN_SWID", "swid"]
    
    s2 = None
    s2_source = None
    for var in s2_vars:
        s2 = _env(var)
        if s2:
            s2_source = var
            break
    
    swid = None
    swid_source = None
    for var in swid_vars:
        swid = _env(var)
        if swid:
            swid_source = var
            break
    
    # Validate credentials
    if not s2:
        log.error(f"ESPN S2 cookie not found. Tried: {', '.join(s2_vars)}")
        log.error("Get this from your browser cookies when logged into ESPN Fantasy")
        return None
    
    if not swid:
        log.error(f"SWID not found. Tried: {', '.join(swid_vars)}")
        log.error("Get this from your browser cookies when logged into ESPN Fantasy")
        return None
    
    log.info(f"Found ESPN S2 from {s2_source}")
    log.info(f"Found SWID from {swid_source}")
    
    # Create league with retry logic
    max_retries = 3
    for attempt in range(max_retries):
        try:
            log.info(f"Creating League object (attempt {attempt + 1}/{max_retries})")
            league = League(league_id=league_id, year=year, espn_s2=s2, swid=swid)
            
            # Test the connection by accessing teams
            teams = league.teams
            league_name = getattr(league.settings, 'name', 'Unknown League')
            
            log.info(f"✅ League created successfully: '{league_name}' with {len(teams)} teams")
            return league
            
        except Exception as e:
            log.error(f"League creation attempt {attempt + 1} failed: {e}")
            
            if attempt == max_retries - 1:
                log.error("All league creation attempts failed")
                log.error("Check your league ID, year, and ESPN credentials")
                return None
            else:
                log.info(f"Retrying in 2 seconds...")
                time.sleep(2)
    
    return None


# ------------------- Core Data Fetching -------------------

def fetch_week_from_espn(league: Any, year: int, week: int) -> Dict[str, Any]:
    """
    Fetch league data for a specific week with robust error handling
    Returns a dict with LEAGUE_NAME and GAMES (list of game dicts)
    Each game has stringified scores for docxtpl compatibility
    """
    result: Dict[str, Any] = {
        "LEAGUE_NAME": "",
        "GAMES": []
    }
    
    if not league:
        log.warning("No League object provided; returning empty result")
        return result

    # Get league name with multiple fallback strategies
    league_name = ""
    try:
        if hasattr(league, 'settings') and hasattr(league.settings, 'name'):
            league_name = league.settings.name
        elif hasattr(league, 'league_name'):
            league_name = league.league_name
        
        if league_name:
            log.info(f"League name: {league_name}")
        else:
            log.warning("Could not determine league name from ESPN")
            
    except Exception as e:
        log.warning(f"Error getting league name: {e}")
    
    # Use environment fallback if needed
    result["LEAGUE_NAME"] = league_name or _env("LEAGUE_DISPLAY_NAME") or "League"

    # Fetch scoreboard with retry logic
    max_retries = 3
    scoreboard = None
    
    for attempt in range(max_retries):
        try:
            log.info(f"Fetching scoreboard for week {week} (attempt {attempt + 1}/{max_retries})")
            scoreboard = league.scoreboard(week)
            
            if scoreboard is None:
                log.warning(f"Scoreboard returned None for week {week}")
                break
            
            log.info(f"Successfully fetched scoreboard: {len(scoreboard)} matchups found")
            break
            
        except Exception as e:
            log.error(f"Scoreboard fetch attempt {attempt + 1} failed: {e}")
            
            if attempt == max_retries - 1:
                log.error("All scoreboard fetch attempts failed")
                return result
            else:
                log.info("Retrying in 2 seconds...")
                time.sleep(2)
    
    # Process games
    if not scoreboard:
        log.warning("No scoreboard data available")
        return result
    
    games: List[Dict[str, Any]] = []
    
    for i, matchup in enumerate(scoreboard):
        try:
            # Extract team information
            home_team = getattr(matchup, "home_team", None)
            away_team = getattr(matchup, "away_team", None)
            
            # Extract scores with fallbacks
            home_score = getattr(matchup, "home_score", 0.0)
            away_score = getattr(matchup, "away_score", 0.0)
            
            # Create game entry
            game = {
                "HOME_TEAM_NAME": _team_display_name(home_team),
                "AWAY_TEAM_NAME": _team_display_name(away_team),
                "HOME_SCORE": _coerce_str(home_score),
                "AWAY_SCORE": _coerce_str(away_score),
                
                # Placeholder fields for spotlight data
                "TOP_HOME": "",
                "TOP_AWAY": "", 
                "BUST": "",
                "KEYPLAY": "",
                "DEF": "",
                "RECAP": "",
                "BLURB": ""
            }
            
            games.append(game)
            
            log.debug(f"Processed game {i+1}: {game['HOME_TEAM_NAME']} ({game['HOME_SCORE']}) vs {game['AWAY_TEAM_NAME']} ({game['AWAY_SCORE']})")
            
        except Exception as e:
            log.error(f"Error processing matchup {i+1}: {e}")
            # Continue processing other games
            continue
    
    result["GAMES"] = games
    log.info(f"Successfully processed {len(games)} games for week {week}")
    
    return result


# ------------------- Awards Calculation -------------------

def _compute_weekly_awards(games: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Calculate weekly awards from team scores:
    - CUPCAKE: Lowest single-team score 
    - KITTY: Largest losing margin
    - TOPSCORE: Highest single-team score
    
    Returns formatted strings ready for template insertion
    """
    if not games:
        return {
            "CUPCAKE": "—",
            "KITTY": "—", 
            "TOPSCORE": "—"
        }
    
    # Collect all scores and margins
    all_scores: List[Tuple[str, float]] = []  # (team_name, score)
    losing_margins: List[Tuple[str, str, float]] = []  # (loser, winner, margin)
    
    for game in games:
        home_name = game.get("HOME_TEAM_NAME", "Home")
        away_name = game.get("AWAY_TEAM_NAME", "Away")
        
        home_score = _float_or_none(game.get("HOME_SCORE"))
        away_score = _float_or_none(game.get("AWAY_SCORE"))
        
        # Add to all scores if valid
        if home_score is not None:
            all_scores.append((home_name, home_score))
        if away_score is not None:
            all_scores.append((away_name, away_score))
        
        # Calculate margin if both scores valid
        if home_score is not None and away_score is not None:
            if home_score > away_score:
                margin = home_score - away_score
                losing_margins.append((away_name, home_name, margin))
            elif away_score > home_score:
                margin = away_score - home_score
                losing_margins.append((home_name, away_name, margin))
            # No margin added for ties
    
    # Calculate awards
    awards = {}
    
    # Cupcake Award (lowest score)
    if all_scores:
        loser_name, lowest_score = min(all_scores, key=lambda x: x[1])
        score_str = f"{lowest_score:.2f}".rstrip("0").rstrip(".")
        awards["CUPCAKE"] = f"{loser_name} — {score_str}"
    else:
        awards["CUPCAKE"] = "—"
    
    # Kitty Award (biggest blowout)
    if losing_margins:
        loser_name, winner_name, biggest_margin = max(losing_margins, key=lambda x: x[2])
        margin_str = f"{biggest_margin:.2f}".rstrip("0").rstrip(".")
        awards["KITTY"] = f"{loser_name} to {winner_name} — {margin_str}"
    else:
        awards["KITTY"] = "—"
    
    # Top Score Award
    if all_scores:
        winner_name, highest_score = max(all_scores, key=lambda x: x[1])
        score_str = f"{highest_score:.2f}".rstrip("0").rstrip(".")
        awards["TOPSCORE"] = f"{winner_name} — {score_str}"
    else:
        awards["TOPSCORE"] = "—"
    
    log.info(f"Calculated awards - Cupcake: {awards['CUPCAKE']}, Kitty: {awards['KITTY']}, Top: {awards['TOPSCORE']}")
    
    return awards


# ------------------- Public Interface -------------------

def assemble_context(league_id: str, year: int, week: int, 
                    llm_blurbs: bool = False, blurb_style: str = "sabre") -> Dict[str, Any]:
    """
    Main function to assemble complete context for template rendering
    
    Args:
        league_id: ESPN League ID (as string)
        year: Season year
        week: Week number
        llm_blurbs: Whether to generate LLM blurbs (handled elsewhere)
        blurb_style: Style for blurbs (passed through, handled elsewhere)
    
    Returns:
        Dict with template context including:
        - LEAGUE_NAME: League display name
        - WEEK_NUMBER: Week number
        - WEEKLY_INTRO: Standard intro text
        - GAMES: List of game dicts with scores and placeholder fields
        - CUPCAKE/KITTY/TOPSCORE: Award strings
    """
    # Initialize context with defaults
    context: Dict[str, Any] = {
        "LEAGUE_NAME": _env("LEAGUE_DISPLAY_NAME") or "League",
        "WEEK_NUMBER": week,
        "WEEKLY_INTRO": f"Week {week} delivered thrilling fantasy performances across head-to-head battles.",
        "GAMES": [],
        "CUPCAKE": "—",
        "KITTY": "—", 
        "TOPSCORE": "—"
    }
    
    # Convert league_id to int
    try:
        league_id_int = int(league_id)
    except (ValueError, TypeError):
        log.error(f"Invalid league_id: {league_id}")
        return context
    
    # Create league and fetch data
    league = _make_league(league_id_int, year)
    if league:
        live_data = fetch_week_from_espn(league, year, week)
        
        # Update context with live data
        if live_data.get("LEAGUE_NAME"):
            context["LEAGUE_NAME"] = live_data["LEAGUE_NAME"]
        
        if live_data.get("GAMES"):
            context["GAMES"] = live_data["GAMES"]
    else:
        log.warning("Could not create league object; using empty game data")
    
    # Calculate weekly awards from available game data
    if context["GAMES"]:
        awards = _compute_weekly_awards(context["GAMES"])
        context.update(awards)
    else:
        log.warning("No games found; cannot compute weekly awards")
    
    log.info(f"Context assembled for {context['LEAGUE_NAME']} Week {week}: {len(context['GAMES'])} games")
    
    return context


# ------------------- Backwards Compatibility -------------------

# Alias for backwards compatibility
build_context = assemble_context


# ------------------- Utility Functions -------------------

def validate_week_data(context: Dict[str, Any]) -> bool:
    """
    Validate that the context contains usable data
    
    Returns:
        True if context has valid game data, False otherwise
    """
    games = context.get("GAMES", [])
    
    if not games:
        log.warning("No games found in context")
        return False
    
    # Check if games have required fields
    required_fields = ["HOME_TEAM_NAME", "AWAY_TEAM_NAME", "HOME_SCORE", "AWAY_SCORE"]
    
    for i, game in enumerate(games):
        missing_fields = [field for field in required_fields if not game.get(field)]
        if missing_fields:
            log.warning(f"Game {i+1} missing fields: {missing_fields}")
            return False
    
    log.info(f"Validation passed: {len(games)} valid games found")
    return True


def get_league_info(league_id: int, year: int) -> Dict[str, Any]:
    """
    Get basic league information without fetching game data
    Useful for testing connections
    
    Returns:
        Dict with league_name, team_count, and success status
    """
    result = {
        "success": False,
        "league_name": "",
        "team_count": 0,
        "error": ""
    }
    
    try:
        league = _make_league(league_id, year)
        if league:
            result["success"] = True
            result["league_name"] = getattr(league.settings, 'name', 'Unknown League')
            result["team_count"] = len(league.teams) if hasattr(league, 'teams') else 0
        else:
            result["error"] = "Could not create league object"
            
    except Exception as e:
        result["error"] = str(e)
        log.error(f"Error getting league info: {e}")
    
    return result


def test_week_availability(league_id: int, year: int, week: int) -> bool:
    """
    Test if a specific week's data is available
    
    Returns:
        True if week data is accessible, False otherwise
    """
    try:
        league = _make_league(league_id, year)
        if not league:
            return False
        
        scoreboard = league.scoreboard(week)
        return scoreboard is not None and len(scoreboard) > 0
        
    except Exception as e:
        log.error(f"Error testing week {week}: {e}")
        return False


# ------------------- Debug Functions -------------------

def debug_dump_context(context: Dict[str, Any]) -> str:
    """
    Create a debug dump of the context for troubleshooting
    
    Returns:
        Formatted string with context details
    """
    lines = [
        f"League: {context.get('LEAGUE_NAME', 'Unknown')}",
        f"Week: {context.get('WEEK_NUMBER', 'Unknown')}",
        f"Games: {len(context.get('GAMES', []))}",
        ""
    ]
    
    games = context.get('GAMES', [])
    for i, game in enumerate(games, 1):
        lines.append(f"Game {i}:")
        lines.append(f"  {game.get('HOME_TEAM_NAME', '?')} ({game.get('HOME_SCORE', '?')}) vs")
        lines.append(f"  {game.get('AWAY_TEAM_NAME', '?')} ({game.get('AWAY_SCORE', '?')})")
        lines.append("")
    
    lines.extend([
        "Awards:",
        f"  Cupcake: {context.get('CUPCAKE', '?')}",
        f"  Kitty: {context.get('KITTY', '?')}",
        f"  Top Score: {context.get('TOPSCORE', '?')}"
    ])
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Simple test when run directly
    import sys
    
    if len(sys.argv) != 4:
        print("Usage: python gazette_data.py <league_id> <year> <week>")
        sys.exit(1)
    
    league_id = int(sys.argv[1])
    year = int(sys.argv[2])
    week = int(sys.argv[3])
    
    print(f"Testing data fetch for League {league_id}, Year {year}, Week {week}")
    print("=" * 60)
    
    context = assemble_context(str(league_id), year, week)
    print(debug_dump_context(context))
    
    if validate_week_data(context):
        print("\n✅ Data validation passed")
    else:
        print("\n❌ Data validation failed")