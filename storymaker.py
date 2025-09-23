#!/usr/bin/env python3
"""
storymaker.py - Enhanced LLM commentary generation for Gridiron Gazette

Improvements:
- Better error handling and retry logic
- Enhanced prompts for different styles
- Fallback mechanisms when API fails
- Support for multiple OpenAI SDK versions
- Rate limiting and cost optimization
"""

from __future__ import annotations
import os
import time
import logging
from typing import List, Dict, Any, Optional

log = logging.getLogger("storymaker")

# OpenAI SDK detection and import
_OPENAI_NEW = False
try:
    from openai import OpenAI
    _OPENAI_NEW = True
    log.info("Using modern OpenAI SDK")
except ImportError:
    try:
        import openai
        log.info("Using legacy OpenAI SDK")
    except ImportError:
        openai = None
        log.warning("OpenAI SDK not available")


# ------------------- Prompt Templates -------------------

def _load_sabre_prompt(week: int) -> str:
    """Load Sabre's signature prompt style"""
    custom_prompt = os.getenv("GAZETTE_SABRE_PROMPT")
    if custom_prompt:
        return custom_prompt.strip()
    
    return (
        f"You are Sabre, the Gridiron Gazette's witty Doberman mascot and beat reporter. "
        f"Write in first-person as Sabre with a clean, clever voice that's informative but fun. "
        f"Focus on the game data provided - don't invent stats or players. "
        f"Highlight the decisive moments, standout performances, and any notable letdowns. "
        f"Keep it conversational but sharp. "
        f"Always end with 'Sabre out—see you in Week {week}.'"
    )

def _load_neutral_prompt() -> str:
    """Load neutral commentary prompt"""
    return (
        "Write a concise, professional fantasy football game recap. "
        "Focus on key performances and game-deciding moments. "
        "Use the provided data accurately without embellishment. "
        "Keep tone informative and objective."
    )

def _load_hype_prompt() -> str:
    """Load high-energy hype prompt"""
    return (
        "Write an energetic, exciting fantasy football recap! "
        "Emphasize the drama, the clutch performances, and the crushing defeats. "
        "Use dynamic language that captures the intensity of fantasy competition. "
        "Make every game sound like an epic battle!"
    )

def _get_system_prompt(style: str, week: int) -> str:
    """Get appropriate system prompt based on style"""
    style_lower = style.lower()
    
    if style_lower == "sabre":
        return _load_sabre_prompt(week)
    elif style_lower == "neutral":
        return _load_neutral_prompt()
    elif style_lower == "hype":
        return _load_hype_prompt()
    else:
        log.warning(f"Unknown style '{style}', using neutral")
        return _load_neutral_prompt()


# ------------------- Player Data Helpers -------------------

def _player_line(player: Any) -> str:
    """Format player performance line"""
    try:
        points = getattr(player, "points", getattr(player, "total_points", 0)) or 0
        projected = getattr(player, "projected_total_points", getattr(player, "projected_points", 0)) or 0
        name = getattr(player, "name", "Unknown Player")
        
        if projected > 0:
            return f"{name} ({points:.1f} vs {projected:.1f} proj)"
        else:
            return f"{name} ({points:.1f} pts)"
    except Exception:
        return f"{getattr(player, 'name', 'Unknown')} (stats unavailable)"


# ------------------- Context Builders -------------------

def _from_league_matchup(matchup: Any, year: int, week: int, max_words: int) -> str:
    """Build context from ESPN League matchup object with player details"""
    try:
        home_team = getattr(matchup, "home_team", None)
        away_team = getattr(matchup, "away_team", None)
        home_score = getattr(matchup, "home_score", 0)
        away_score = getattr(matchup, "away_score", 0)
        
        home_name = getattr(home_team, "team_name", "Home") if home_team else "Home"
        away_name = getattr(away_team, "team_name", "Away") if away_team else "Away"
        
        lines = [
            f"Season {year}, Week {week}.",
            f"{home_name} ({home_score:.1f}) vs {away_name} ({away_score:.1f})."
        ]
        
        # Add top performers if available
        for team, label in [(home_team, "Home"), (away_team, "Away")]:
            if team:
                starters = getattr(team, "starters", []) or []
                if starters:
                    try:
                        top_player = max(starters, 
                                       key=lambda p: getattr(p, "points", getattr(p, "total_points", 0)) or 0)
                        lines.append(f"{label} top performer: {_player_line(top_player)}.")
                    except Exception:
                        pass
        
        lines.append(f"Write approximately {max_words} words.")
        return "\n".join(lines)
        
    except Exception as e:
        log.error(f"Error building league matchup context: {e}")
        return f"Season {year}, Week {week}. Game data unavailable. Write {max_words} words."

def _from_games_entry(game: Dict[str, Any], year: int, week: int, max_words: int) -> str:
    """Build context from simplified game entry (team scores only)"""
    try:
        home_name = game.get("HOME_TEAM_NAME", "Home")
        away_name = game.get("AWAY_TEAM_NAME", "Away")
        home_score = game.get("HOME_SCORE", "0")
        away_score = game.get("AWAY_SCORE", "0")
        
        return (
            f"Season {year}, Week {week}. "
            f"{home_name} ({home_score}) vs {away_name} ({away_score}). "
            f"Use only the provided team names and scores. "
            f"Write approximately {max_words} words."
        )
    except Exception as e:
        log.error(f"Error building game entry context: {e}")
        return f"Season {year}, Week {week}. Write {max_words} words about this fantasy matchup."


# ------------------- OpenAI API Handling -------------------

def _call_openai(messages: List[Dict[str, str]], max_retries: int = 2) -> str:
    """
    Call OpenAI API with retry logic and error handling
    Supports both modern and legacy OpenAI SDK versions
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable not set")
    
    model = os.getenv("GAZETTE_LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
    
    for attempt in range(max_retries + 1):
        try:
            if _OPENAI_NEW:
                # Modern OpenAI SDK (v1.0+)
                client = OpenAI(api_key=api_key)
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=500
                )
                return (response.choices[0].message.content or "").strip()
            
            elif openai:
                # Legacy OpenAI SDK
                openai.api_key = api_key
                response = openai.ChatCompletion.create(
                    model=model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=500
                )
                return (response["choices"][0]["message"]["content"] or "").strip()
            
            else:
                raise RuntimeError("OpenAI SDK not installed. Install with: pip install openai")
                
        except Exception as e:
            log.error(f"OpenAI API call attempt {attempt + 1} failed: {e}")
            
            if attempt < max_retries:
                wait_time = 2 ** attempt  # Exponential backoff
                log.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                raise RuntimeError(f"OpenAI API failed after {max_retries + 1} attempts: {e}")


# ------------------- Fallback Content -------------------

def _generate_fallback_blurb(game_data: Dict[str, Any], week: int, style: str) -> str:
    """Generate fallback blurb when API is unavailable"""
    try:
        home_name = game_data.get("HOME_TEAM_NAME", "Home")
        away_name = game_data.get("AWAY_TEAM_NAME", "Away")
        home_score = game_data.get("HOME_SCORE", "0")
        away_score = game_data.get("AWAY_SCORE", "0")
        
        if style.lower() == "sabre":
            return (
                f"Week {week}: {home_name} {home_score} vs {away_name} {away_score}. "
                f"A solid fantasy battle with both teams putting up respectable numbers. "
                f"Sabre out—see you in Week {week}."
            )
        elif style.lower() == "hype":
            return (
                f"EPIC CLASH! {home_name} ({home_score}) vs {away_name} ({away_score}) "
                f"in Week {week}! Fantasy fireworks and competitive action!"
            )
        else:
            return (
                f"Week {week} matchup: {home_name} scored {home_score} points "
                f"against {away_name}'s {away_score} points."
            )
            
    except Exception:
        return f"Week {week} fantasy matchup completed."


# ------------------- Main Generation Function -------------------

def generate_blurbs(
    league: Any,
    year: int,
    week: int,
    style: str = "sabre",
    max_words: int = 200,
    games: Optional[List[Dict[str, Any]]] = None
) -> List[str]:
    """
    Generate commentary blurbs for fantasy games
    
    Args:
        league: ESPN League object (can be None)
        year: Season year
        week: Week number
        style: Commentary style ("sabre", "neutral", "hype")
        max_words: Target words per blurb
        games: Fallback game data (team scores only)
    
    Returns:
        List of commentary strings, one per game
    """
    log.info(f"Generating {style} blurbs for Week {week}")
    
    system_prompt = _get_system_prompt(style, week)
    blurbs: List[str] = []
    api_available = True
    
    # Check if API is available
    try:
        if not os.getenv("OPENAI_API_KEY"):
            log.warning("No OpenAI API key provided")
            api_available = False
        elif not (_OPENAI_NEW or openai):
            log.warning("OpenAI SDK not available")
            api_available = False
    except Exception:
        api_available = False
    
    # Strategy 1: Try league-based generation (with player details)
    if league and api_available:
        try:
            log.info("Attempting league-based blurb generation with player details")
            scoreboard = league.scoreboard(week)
            
            for i, matchup in enumerate(scoreboard):
                try:
                    user_context = _from_league_matchup(matchup, year, week, max_words)
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_context}
                    ]
                    
                    blurb = _call_openai(messages)
                    blurbs.append(blurb)
                    log.debug(f"Generated league-based blurb for game {i+1}")
                    
                    # Small delay to avoid rate limiting
                    if i < len(scoreboard) - 1:
                        time.sleep(0.5)
                        
                except Exception as e:
                    log.error(f"Failed to generate league-based blurb for game {i+1}: {e}")
                    # Fall back to simplified generation for this game
                    if games and i < len(games):
                        fallback_blurb = _generate_fallback_blurb(games[i], week, style)
                        blurbs.append(fallback_blurb)
                    else:
                        blurbs.append(f"Week {week} matchup completed.")
            
            if blurbs:
                log.info(f"Successfully generated {len(blurbs)} league-based blurbs")
                return blurbs
                
        except Exception as e:
            log.error(f"League-based generation failed: {e}")
            blurbs = []  # Reset for fallback
    
    # Strategy 2: Try games-based generation (team scores only)
    if games and api_available:
        try:
            log.info("Attempting games-based blurb generation with team scores")
            
            for i, game in enumerate(games):
                try:
                    user_context = _from_games_entry(game, year, week, max_words)
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_context}
                    ]
                    
                    blurb = _call_openai(messages)
                    blurbs.append(blurb)
                    log.debug(f"Generated games-based blurb for game {i+1}")
                    
                    # Small delay to avoid rate limiting
                    if i < len(games) - 1:
                        time.sleep(0.5)
                        
                except Exception as e:
                    log.error(f"Failed to generate games-based blurb for game {i+1}: {e}")
                    fallback_blurb = _generate_fallback_blurb(game, week, style)
                    blurbs.append(fallback_blurb)
            
            if blurbs:
                log.info(f"Successfully generated {len(blurbs)} games-based blurbs")
                return blurbs
                
        except Exception as e:
            log.error(f"Games-based generation failed: {e}")
            blurbs = []  # Reset for final fallback
    
    # Strategy 3: Fallback generation (no API)
    log.warning("Using fallback blurb generation (no API available)")
    
    if games:
        for i, game in enumerate(games):
            fallback_blurb = _generate_fallback_blurb(game, week, style)
            blurbs.append(fallback_blurb)
        log.info(f"Generated {len(blurbs)} fallback blurbs")
    else:
        # Ultimate fallback - generic blurbs
        log.warning("No game data available, using generic blurbs")
        fallback_count = 6  # Assume 6 games typical
        for i in range(fallback_count):
            if style.lower() == "sabre":
                blurb = f"Week {week} brought some solid fantasy action. Sabre out—see you in Week {week}."
            else:
                blurb = f"Week {week} fantasy matchup completed."
            blurbs.append(blurb)
    
    return blurbs


# ------------------- Testing and Utilities -------------------

def test_api_connection() -> bool:
    """Test if OpenAI API is working"""
    try:
        if not os.getenv("OPENAI_API_KEY"):
            log.error("No OpenAI API key provided")
            return False
        
        test_messages = [
            {"role": "user", "content": "Respond with exactly: 'API test successful'"}
        ]
        
        result = _call_openai(test_messages, max_retries=1)
        success = "API test successful" in result
        
        if success:
            log.info("OpenAI API test successful")
        else:
            log.warning(f"OpenAI API test returned unexpected result: {result}")
        
        return success
        
    except Exception as e:
        log.error(f"OpenAI API test failed: {e}")
        return False


def estimate_cost(num_games: int, words_per_game: int = 200) -> float:
    """Estimate OpenAI API cost for generating blurbs"""
    # Rough estimation based on GPT-4o-mini pricing
    tokens_per_game = words_per_game * 1.3  # ~1.3 tokens per word
    total_tokens = num_games * tokens_per_game
    
    # GPT-4o-mini: ~$0.000150 per 1K input tokens, ~$0.000600 per 1K output tokens
    estimated_cost = (total_tokens / 1000) * 0.0008  # Average cost
    
    return estimated_cost


# ------------------- CLI Interface -------------------

if __name__ == "__main__":
    import sys
    
    # Simple test interface
    if len(sys.argv) == 2 and sys.argv[1] == "test":
        print("Testing OpenAI API connection...")
        if test_api_connection():
            print("✅ API connection successful")
        else:
            print("❌ API connection failed")
        sys.exit(0)
    
    if len(sys.argv) < 4:
        print("Usage: python storymaker.py <year> <week> <style> [test]")
        print("Styles: sabre, neutral, hype")
        print("       python storymaker.py test")
        sys.exit(1)
    
    year = int(sys.argv[1])
    week = int(sys.argv[2])
    style = sys.argv[3]
    
    # Test with sample game data
    sample_games = [
        {
            "HOME_TEAM_NAME": "Team Alpha",
            "AWAY_TEAM_NAME": "Team Beta", 
            "HOME_SCORE": "125.5",
            "AWAY_SCORE": "118.2"
        }
    ]
    
    print(f"Generating sample {style} blurb for Week {week}...")
    
    try:
        blurbs = generate_blurbs(
            league=None,
            year=year,
            week=week,
            style=style,
            max_words=150,
            games=sample_games
        )
        
        print("\nGenerated blurb:")
        print("-" * 50)
        print(blurbs[0] if blurbs else "No blurb generated")
        print("-" * 50)
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)