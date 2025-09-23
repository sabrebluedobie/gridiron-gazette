#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional
import time
import logging
import json
import re

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

import gazette_data
import logo_resolver
import storymaker

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _safe(s): 
    return s or ""

def _inline(doc, path: Optional[str], w_mm: float) -> Optional[InlineImage]:
    p = Path(path) if path else None
    return InlineImage(doc, str(p), width=Mm(w_mm)) if (p and p.exists()) else None

def safe_get_score_enhanced(team, week, team_name="Unknown"):
    """Enhanced score extraction that works with ESPN API quirks"""
    try:
        logger.debug(f"Getting score for {team_name}")
        
        # Method 1: scores dictionary with week key
        if hasattr(team, 'scores') and isinstance(team.scores, dict):
            if week in team.scores:
                score = team.scores[week]
                if score is not None:
                    logger.info(f"✅ Found score via scores[{week}] for {team_name}: {score}")
                    return f"{float(score):.1f}"
            
            # Try latest week if specific week not found
            if team.scores:
                latest_week = max(team.scores.keys())
                score = team.scores[latest_week]
                if score is not None:
                    logger.info(f"✅ Using latest week {latest_week} score for {team_name}: {score}")
                    return f"{float(score):.1f}"
        
        # Method 2: points attribute
        if hasattr(team, 'points') and team.points is not None:
            logger.info(f"✅ Found score via points for {team_name}: {team.points}")
            return f"{float(team.points):.1f}"
        
        # Method 3: total_points
        if hasattr(team, 'total_points') and team.total_points is not None:
            logger.info(f"✅ Found score via total_points for {team_name}: {team.total_points}")
            return f"{float(team.total_points):.1f}"
        
        logger.warning(f"❌ No score found for {team_name}")
        return ""
        
    except Exception as e:
        logger.error(f"❌ Error getting score for {team_name}: {e}")
        return ""

def load_team_mapping():
    """Load team_logos.json as authoritative source"""
    mapping_file = Path("team_logos.json")
    if not mapping_file.exists():
        logger.warning("team_logos.json not found")
        return {}
    
    try:
        with open(mapping_file, 'r', encoding='utf-8') as f:
            mapping = json.load(f)
        logger.info(f"Loaded {len(mapping)} team logo mappings from team_logos.json")
        return mapping
    except Exception as e:
        logger.error(f"Error loading team_logos.json: {e}")
        return {}

def normalize_team_name_for_logo(name):
    """Normalize team name for emoji handling in logos"""
    if not name:
        return ""
    
    # Common emoji to underscore conversions
    replacements = {
        '🏆': '_', '💀': '_', '🏉': '_', '🎯': '_', '⚡': '_',
        '🔥': '_', '💯': '_', '👑': '_', '🚀': '_', '⭐': '_',
        '💪': '_', '🎉': '_', '🌟': '_', '🦅': '_', '🐻': '_'
    }
    
    normalized = str(name)
    for emoji, replacement in replacements.items():
        normalized = normalized.replace(emoji, replacement)
    
    return normalized

def get_team_logo_from_mapping(team_name):
    """Get team logo using team_logos.json as source of truth"""
    if not team_name:
        return None
    
    mapping = load_team_mapping()
    if not mapping:
        return logo_resolver.team_logo(team_name)
    
    # Try exact match first
    if team_name in mapping:
        logo_path = Path(mapping[team_name])
        if logo_path.exists():
            logger.debug(f"Found exact logo match for '{team_name}': {logo_path}")
            return str(logo_path)
    
    # Try normalized match (for emoji teams)
    normalized = normalize_team_name_for_logo(team_name)
    if normalized != team_name and normalized in mapping:
        logo_path = Path(mapping[normalized])
        if logo_path.exists():
            logger.debug(f"Found normalized logo match for '{team_name}' -> '{normalized}': {logo_path}")
            return str(logo_path)
    
    # Try partial matching
    for mapped_name, path in mapping.items():
        if team_name.lower() in mapped_name.lower() or mapped_name.lower() in team_name.lower():
            logo_path = Path(path)
            if logo_path.exists():
                logger.debug(f"Found partial logo match for '{team_name}' -> '{mapped_name}': {logo_path}")
                return str(logo_path)
    
    logger.warning(f"No logo mapping found for '{team_name}' in team_logos.json, using fallback")
    return logo_resolver.team_logo(team_name)

def _attach_team_logos(doc, games: List[Dict[str, Any]]) -> None:
    """Attach team logos using team_logos.json as source of truth"""
    for g in games:
        home_team = g.get("HOME_TEAM_NAME", "")
        away_team = g.get("AWAY_TEAM_NAME", "")
        
        home_logo_path = get_team_logo_from_mapping(home_team)
        away_logo_path = get_team_logo_from_mapping(away_team)
        
        g["HOME_LOGO"] = _inline(doc, home_logo_path, 22.0)
        g["AWAY_LOGO"] = _inline(doc, away_logo_path, 22.0)
        
        if home_logo_path:
            logger.debug(f"Home logo for {home_team}: {Path(home_logo_path).name}")
        if away_logo_path:
            logger.debug(f"Away logo for {away_team}: {Path(away_logo_path).name}")

def _attach_special_logos(doc, ctx: Dict[str, Any]) -> None:
    mapping = load_team_mapping()
    
    league_name = ctx.get("LEAGUE_NAME") or ctx.get("LEAGUE_LOGO_NAME") or "Gridiron Gazette"
    
    # Check if league/sponsor logos are in team_logos.json
    league_logo_path = mapping.get("LEAGUE_LOGO") or logo_resolver.league_logo(league_name)
    sponsor_logo_path = mapping.get("SPONSOR_LOGO") or logo_resolver.sponsor_logo("Gridiron Gazette")
    
    ctx["LEAGUE_LOGO"] = _inline(doc, league_logo_path, 28.0)
    ctx["SPONSOR_LOGO"] = _inline(doc, sponsor_logo_path, 26.0)

def _map_front_page_slots(ctx: Dict[str, Any]) -> None:
    games = ctx.get("GAMES", [])
    for i in range(10):
        g = games[i] if i < len(games) else {}
        n = i + 1
        ctx[f"MATCHUP{n}_HOME"] = _safe(g.get("HOME_TEAM_NAME"))
        ctx[f"MATCHUP{n}_AWAY"] = _safe(g.get("AWAY_TEAM_NAME"))
        ctx[f"MATCHUP{n}_HS"]   = _safe(g.get("HOME_SCORE"))
        ctx[f"MATCHUP{n}_AS"]   = _safe(g.get("AWAY_SCORE"))
        ctx[f"MATCHUP{n}_HOME_LOGO"] = g.get("HOME_LOGO")
        ctx[f"MATCHUP{n}_AWAY_LOGO"] = g.get("AWAY_LOGO")
        ctx[f"MATCHUP{n}_BLURB"]     = _safe(g.get("RECAP") or g.get("BLURB"))
        ctx[f"MATCHUP{n}_TOP_HOME"]  = _safe(g.get("TOP_HOME"))
        ctx[f"MATCHUP{n}_TOP_AWAY"]  = _safe(g.get("TOP_AWAY"))
        ctx[f"MATCHUP{n}_BUST"]      = _safe(g.get("BUST"))
        ctx[f"MATCHUP{n}_KEYPLAY"]   = _safe(g.get("KEYPLAY") or g.get("KEY_PLAY"))
        ctx[f"MATCHUP{n}_DEF"]       = _safe(g.get("DEF") or g.get("DEF_NOTE"))

# ===== ENHANCED PLAYER STATS FUNCTIONS =====

def get_all_players(team, team_name):
    """Get all relevant players from a team with maximum fallbacks"""
    players = []
    
    try:
        # Try multiple player sources in order of preference
        sources_to_try = [
            ('lineup', 'lineup'),
            ('roster', 'roster'), 
            ('box_players', 'box_players'),
            ('starters', 'starters')
        ]
        
        for source_name, attr_name in sources_to_try:
            if hasattr(team, attr_name):
                player_list = getattr(team, attr_name)
                if player_list and len(player_list) > 0:
                    logger.info(f"Found {len(player_list)} players in {source_name} for {team_name}")
                    
                    # If it's lineup, filter to starters
                    if source_name == 'lineup':
                        starters = [p for p in player_list if is_starter(p)]
                        if starters:
                            logger.info(f"Filtered to {len(starters)} starters for {team_name}")
                            return starters
                        else:
                            # Take first 9 if no starter info available
                            logger.info(f"No starter info, taking first 9 for {team_name}")
                            return player_list[:9]
                    else:
                        # For roster/other sources, take first 9
                        return player_list[:9]
        
        logger.warning(f"No players found for {team_name}")
        return []
        
    except Exception as e:
        logger.error(f"Error getting players for {team_name}: {e}")
        return []

def is_starter(player):
    """Check if player is a starter (not bench/IR)"""
    try:
        # Method 1: slot_position
        if hasattr(player, 'slot_position'):
            slot = str(player.slot_position).upper()
            bench_slots = ['BE', 'IR', 'BENCH', 'BN', '20', 'BENCH', 'Bench']
            return slot not in bench_slots
        
        # Method 2: lineup_slot
        if hasattr(player, 'lineup_slot'):
            slot = str(player.lineup_slot).upper()
            bench_slots = ['BE', 'IR', 'BENCH', 'BN', '20', 'Bench']
            return slot not in bench_slots
            
        # Method 3: Check lineupSlot (ESPN API)
        if hasattr(player, 'lineupSlot'):
            return player.lineupSlot != 20  # 20 is typically bench
            
        # Default: assume starter if we can't determine
        return True
    except Exception as e:
        logger.debug(f"Error checking starter status: {e}")
        return True

def get_player_points(player):
    """Get player points with all possible fallback methods"""
    try:
        # Method 1: Direct points attribute
        if hasattr(player, 'points') and player.points is not None:
            return float(player.points)
        
        # Method 2: total_points
        if hasattr(player, 'total_points') and player.total_points is not None:
            return float(player.total_points)
            
        # Method 3: fantasy_points
        if hasattr(player, 'fantasy_points') and player.fantasy_points is not None:
            return float(player.fantasy_points)
            
        # Method 4: score attribute
        if hasattr(player, 'score') and player.score is not None:
            return float(player.score)
        
        # Method 5: stats dictionary
        if hasattr(player, 'stats') and isinstance(player.stats, dict):
            for key in ['points', 'total_points', 'fantasy_points', 'score']:
                if key in player.stats and player.stats[key] is not None:
                    return float(player.stats[key])
        
        # Method 6: Try breakdown/totals
        if hasattr(player, 'breakdown') and isinstance(player.breakdown, dict):
            total = 0
            for key, value in player.breakdown.items():
                if isinstance(value, (int, float)):
                    total += value
            if total > 0:
                return total
        
        # Method 7: appliedStats (ESPN specific)
        if hasattr(player, 'appliedStats') and isinstance(player.appliedStats, dict):
            total = sum(v for v in player.appliedStats.values() if isinstance(v, (int, float)))
            if total > 0:
                return total
        
        return 0.0
    except (ValueError, TypeError, AttributeError) as e:
        logger.debug(f"Error getting points for player: {e}")
        return 0.0

def get_player_projected(player):
    """Get projected points with fallbacks"""
    try:
        # Method 1: projected_points
        if hasattr(player, 'projected_points') and player.projected_points is not None:
            return float(player.projected_points)
            
        # Method 2: projected_total_points  
        if hasattr(player, 'projected_total_points') and player.projected_total_points is not None:
            return float(player.projected_total_points)
            
        # Method 3: projection
        if hasattr(player, 'projection') and player.projection is not None:
            return float(player.projection)
            
        # Method 4: projectedStats
        if hasattr(player, 'projectedStats') and isinstance(player.projectedStats, dict):
            total = sum(v for v in player.projectedStats.values() if isinstance(v, (int, float)))
            if total > 0:
                return total
                    
        return 0.0
    except (ValueError, TypeError, AttributeError):
        return 0.0

def get_player_name(player):
    """Get player name safely"""
    try:
        if hasattr(player, 'name') and player.name:
            return str(player.name)
        elif hasattr(player, 'full_name') and player.full_name:
            return str(player.full_name) 
        elif hasattr(player, 'player_name') and player.player_name:
            return str(player.player_name)
        elif hasattr(player, 'firstName') and hasattr(player, 'lastName'):
            first = getattr(player, 'firstName', '')
            last = getattr(player, 'lastName', '')
            return f"{first} {last}".strip()
        else:
            return "Unknown Player"
    except Exception:
        return "Unknown Player"

def _compute_top_bust_from_board(league: Any, week: int) -> List[Dict[str, str]]:
    """FIXED VERSION - Enhanced player stats extraction with proper return"""
    out = []
    
    try:
        logger.info(f"🔍 Computing player stats for week {week}")
        
        # Get scoreboard with retries
        board = None
        for attempt in range(3):
            try:
                board = league.scoreboard(week)
                if board and len(board) > 0:
                    logger.info(f"✅ Got scoreboard with {len(board)} matchups")
                    break
                else:
                    logger.warning(f"Empty scoreboard on attempt {attempt + 1}")
                time.sleep(1)
            except Exception as e:
                logger.warning(f"Scoreboard attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    time.sleep(2)
        
        if not board:
            logger.error("❌ No scoreboard data available after retries")
            return []
        
        for i, matchup in enumerate(board):
            # CRITICAL: Initialize entry for EVERY matchup
            entry = {"TOP_HOME": "", "TOP_AWAY": "", "BUST": ""}
            
            try:
                home_team = getattr(matchup, 'home_team', None)
                away_team = getattr(matchup, 'away_team', None)
                
                if not home_team or not away_team:
                    logger.warning(f"⚠️ Matchup {i}: Missing team data")
                    out.append(entry)  # Still append empty entry
                    continue
                
                home_name = getattr(home_team, 'team_name', f'Home{i}')
                away_name = getattr(away_team, 'team_name', f'Away{i}')
                
                logger.info(f"📊 Processing matchup {i}: {home_name} vs {away_name}")
                
                # Get HOME team stats
                home_players = get_all_players(home_team, home_name)
                if home_players:
                    top_home = max(home_players, key=lambda p: get_player_points(p))
                    points = get_player_points(top_home)
                    proj = get_player_projected(top_home)
                    name = get_player_name(top_home)
                    
                    if proj > 0:
                        entry["TOP_HOME"] = f"{name} ({points:.1f} vs {proj:.1f} proj)"
                    else:
                        entry["TOP_HOME"] = f"{name} ({points:.1f} pts)"
                    
                    logger.info(f"🏠 Home top scorer: {entry['TOP_HOME']}")
                else:
                    logger.warning(f"No home players found for {home_name}")
                
                # Get AWAY team stats  
                away_players = get_all_players(away_team, away_name)
                if away_players:
                    top_away = max(away_players, key=lambda p: get_player_points(p))
                    points = get_player_points(top_away)
                    proj = get_player_projected(top_away)
                    name = get_player_name(top_away)
                    
                    if proj > 0:
                        entry["TOP_AWAY"] = f"{name} ({points:.1f} vs {proj:.1f} proj)"
                    else:
                        entry["TOP_AWAY"] = f"{name} ({points:.1f} pts)"
                        
                    logger.info(f"🚗 Away top scorer: {entry['TOP_AWAY']}")
                else:
                    logger.warning(f"No away players found for {away_name}")
                
                # Find BUST (biggest underperformer)
                all_players = home_players + away_players
                bust_player = None
                worst_diff = 0
                
                for player in all_players:
                    points = get_player_points(player)
                    proj = get_player_projected(player)
                    
                    if proj > 5:  # Only consider players with meaningful projections
                        diff = points - proj
                        if diff < worst_diff:
                            worst_diff = diff
                            bust_player = player
                
                if bust_player:
                    name = get_player_name(bust_player)
                    points = get_player_points(bust_player)
                    proj = get_player_projected(bust_player)
                    entry["BUST"] = f"{name} ({points:.1f} vs {proj:.1f} proj)"
                    logger.info(f"💥 Biggest bust: {entry['BUST']}")
                else:
                    logger.info(f"No bust found for matchup {i} (no meaningful projections)")
                
                # CRITICAL: Log what we're actually returning
                logger.info(f"🔥 ENTRY FOR MATCHUP {i}: {entry}")
                
            except Exception as e:
                logger.error(f"❌ Error processing matchup {i}: {e}")
                import traceback
                logger.debug(f"Matchup {i} traceback: {traceback.format_exc()}")
            
            # CRITICAL: Always append the entry (even if empty)
            out.append(entry)
    
    except Exception as e:
        logger.error(f"💀 Fatal error in _compute_top_bust_from_board: {e}")
        import traceback
        logger.error(f"Fatal traceback: {traceback.format_exc()}")
    
    logger.info(f"✅ RETURNING stats for {len(out)} matchups: {out}")
    return out

def calculate_weekly_awards_enhanced(games):
    """Enhanced awards calculation that extracts scores from LLM text when API fails"""
    awards = {
        "top_score": {"team": "", "points": ""},
        "low_score": {"team": "", "points": ""},
        "largest_gap": {"desc": "", "gap": ""}
    }
    
    try:
        scores = []
        
        # First try to extract scores from game data (if available)
        for game in games:
            home_team = game.get("HOME_TEAM_NAME", "")
            away_team = game.get("AWAY_TEAM_NAME", "")
            home_score = game.get("HOME_SCORE", "")
            away_score = game.get("AWAY_SCORE", "")
            
            try:
                if home_score and home_team:
                    scores.append((home_team, float(home_score)))
                if away_score and away_team:
                    scores.append((away_team, float(away_score)))
            except (ValueError, TypeError):
                continue
        
        # If no scores from game data, extract from LLM blurbs (they contain the scores!)
        if not scores:
            logger.info("📊 Extracting scores from LLM blurbs...")
            for game in games:
                recap = game.get("RECAP", "")
                home_team = game.get("HOME_TEAM_NAME", "")
                away_team = game.get("AWAY_TEAM_NAME", "")
                
                # Look for various score patterns in the recap text
                score_patterns = [
                    r'(\d+\.?\d*)\s+to\s+(\d+\.?\d*)',  # "95.62 to 95.64"
                    r'(\d+\.?\d*),?\s+while\s+.*?(\d+\.?\d*)',  # "132.82, while Annie 99.14"
                    r'final score[^0-9]*?(\d+\.?\d*)[^0-9]+(\d+\.?\d*)',  # "final score of 99.78 to 82.1"
                    r'(\d+\.?\d*)[^0-9]+vs[^0-9]+(\d+\.?\d*)',  # "132.52 vs 120.16"
                ]
                
                for pattern in score_patterns:
                    match = re.search(pattern, recap, re.IGNORECASE)
                    if match:
                        try:
                            score1, score2 = float(match.group(1)), float(match.group(2))
                            
                            # Try to determine which team gets which score by looking at context
                            if home_team.lower() in recap.lower()[:match.start()]:
                                # Home team mentioned before scores, likely home team gets first score
                                if home_team: scores.append((home_team, score1))
                                if away_team: scores.append((away_team, score2))
                            else:
                                # Away team mentioned first, or use higher score for winner
                                if score1 >= score2:
                                    # First score is higher, likely the winner mentioned first
                                    if "won" in recap.lower() or "beat" in recap.lower() or "defeated" in recap.lower():
                                        winner = home_team if any(word in recap.lower() for word in [home_team.lower()[:5]]) else away_team
                                        if winner == home_team:
                                            scores.append((home_team, score1))
                                            scores.append((away_team, score2))
                                        else:
                                            scores.append((away_team, score1))
                                            scores.append((home_team, score2))
                                    else:
                                        # Default assignment
                                        if home_team: scores.append((home_team, score1))
                                        if away_team: scores.append((away_team, score2))
                                else:
                                    if home_team: scores.append((home_team, score2))
                                    if away_team: scores.append((away_team, score1))
                            
                            logger.info(f"📊 Extracted scores from '{recap[:50]}...': {home_team}={scores[-2][1] if len(scores)>=2 else 'N/A'}, {away_team}={scores[-1][1] if scores else 'N/A'}")
                            break  # Found scores for this game, move to next
                        except (ValueError, IndexError) as e:
                            logger.debug(f"Error parsing scores from pattern: {e}")
                            continue
        
        if scores:
            # Calculate awards
            top_team, top_points = max(scores, key=lambda x: x[1])
            awards["top_score"] = {"team": top_team, "points": f"{top_points:.1f}"}
            
            low_team, low_points = min(scores, key=lambda x: x[1])
            awards["low_score"] = {"team": low_team, "points": f"{low_points:.1f}"}
            
            gap = top_points - low_points
            awards["largest_gap"] = {"desc": f"{top_team} vs {low_team}", "gap": f"{gap:.1f}"}
            
            logger.info(f"🏆 Awards calculated: Top={top_team}({top_points:.1f}), Low={low_team}({low_points:.1f}), Gap={gap:.1f}")
        else:
            logger.warning("❌ No scores found for awards calculation")
    
    except Exception as e:
        logger.error(f"Error calculating enhanced awards: {e}")
        import traceback
        logger.error(f"Awards traceback: {traceback.format_exc()}")
    
    return awards

def build_weekly_recap(
    league: Any,
    league_id: int,
    year: int,
    week: int,
    template: Optional[str] = None,
    output_dir: str = "recaps",
    llm_blurbs: bool = False,
    blurb_style: str = "sabre",
    blurb_words: int = 200,
) -> str:
    """Enhanced build function with comprehensive stats and awards fixing"""
    
    logger.info(f"🏈 Building weekly recap for League {league_id}, Year {year}, Week {week}")
    
    template_path = template or "recap_template.docx"
    if not Path(template_path).exists():
        raise FileNotFoundError(f"Template file not found: {template_path}")
    
    try:
        doc = DocxTemplate(template_path)
        logger.info(f"✅ Template loaded: {template_path}")
    except Exception as e:
        logger.error(f"Failed to load template {template_path}: {e}")
        raise
    
    # Get base context with error handling
    try:
        ctx = gazette_data.assemble_context(
            str(league_id), year, week, 
            llm_blurbs=False, blurb_style=blurb_style
        )
        logger.info(f"✅ Base context assembled with {len(ctx.get('GAMES', []))} games")
    except Exception as e:
        logger.error(f"Failed to assemble base context: {e}")
        # Create minimal fallback context
        ctx = {
            "LEAGUE_ID": str(league_id),
            "YEAR": year,
            "WEEK": week,
            "GAMES": [],
            "LEAGUE_NAME": "Fantasy League",
            "awards": {"top_score": {"team": "", "points": ""}, "low_score": {"team": "", "points": ""}, "largest_gap": {"desc": "", "gap": ""}}
        }
    
    games = ctx.get("GAMES", [])
    
    # Generate LLM blurbs if requested
    if llm_blurbs and games:
        try:
            logger.info(f"🤖 Generating LLM blurbs for {len(games)} games")
            blurbs = storymaker.generate_blurbs(
                league, year, week, 
                style=blurb_style, max_words=blurb_words, games=games
            )
            for i, g in enumerate(games):
                if i < len(blurbs):
                    g["RECAP"] = blurbs[i]
            logger.info("✅ LLM blurbs generated successfully")
        except Exception as e:
            logger.warning(f"⚠️ LLM blurb generation failed, using basic recaps: {e}")
    
    # ===== CRITICAL STATS COMPUTATION =====
    logger.info("🔥 Computing enhanced player stats...")
    try:
        derived = _compute_top_bust_from_board(league, week)
        
        # CRITICAL FIX: Force assignment instead of setdefault
        for i, g in enumerate(games):
            if i < len(derived):
                # FORCE assignment (don't use setdefault)
                g["TOP_HOME"] = derived[i].get("TOP_HOME", "")
                g["TOP_AWAY"] = derived[i].get("TOP_AWAY", "")
                g["BUST"] = derived[i].get("BUST", "")
                
                # Log what we're assigning
                logger.info(f"🔥 ASSIGNED to game {i}: TOP_HOME='{g['TOP_HOME']}', TOP_AWAY='{g['TOP_AWAY']}', BUST='{g['BUST']}'")
            else:
                # Ensure empty values for games without derived stats
                g["TOP_HOME"] = ""
                g["TOP_AWAY"] = ""
                g["BUST"] = ""
        
        logger.info(f"✅ Enhanced {len(derived)} games with player stats")
        
        # Log verification
        for i, g in enumerate(games[:3]):  # Just log first 3
            logger.info(f"VERIFICATION Game {i}: TOP_HOME='{g.get('TOP_HOME', 'MISSING')}', TOP_AWAY='{g.get('TOP_AWAY', 'MISSING')}', BUST='{g.get('BUST', 'MISSING')}'")
        
    except Exception as e:
        logger.error(f"❌ Failed to compute player stats: {e}")
        import traceback
        logger.error(f"Stats computation traceback: {traceback.format_exc()}")
        
        # Add empty stats to maintain template compatibility
        for g in games:
            g["TOP_HOME"] = ""
            g["TOP_AWAY"] = ""
            g["BUST"] = ""

    # ===== CRITICAL AWARDS COMPUTATION =====
    logger.info("🏆 Computing weekly awards (Top Score, Cupcake, Kitty)...")
    try:
        awards = calculate_weekly_awards_enhanced(games)
        
        # Update context with awards
        ctx["awards"] = awards
        
        # Also add individual award fields for template compatibility
        ctx["AWARD_TOP_TEAM"] = awards["top_score"].get("team", "")
        ctx["AWARD_TOP_NOTE"] = awards["top_score"].get("points", "")
        ctx["AWARD_CUPCAKE_TEAM"] = awards["low_score"].get("team", "")
        ctx["AWARD_CUPCAKE_NOTE"] = awards["low_score"].get("points", "")
        ctx["AWARD_KITTY_TEAM"] = awards["largest_gap"].get("desc", "")
        ctx["AWARD_KITTY_NOTE"] = awards["largest_gap"].get("gap", "")
        
        logger.info(f"🏆 Awards computed:")
        logger.info(f"  Top Score: {ctx['AWARD_TOP_TEAM']} ({ctx['AWARD_TOP_NOTE']})")
        logger.info(f"  Cupcake: {ctx['AWARD_CUPCAKE_TEAM']} ({ctx['AWARD_CUPCAKE_NOTE']})")
        logger.info(f"  Kitty: {ctx['AWARD_KITTY_TEAM']} ({ctx['AWARD_KITTY_NOTE']})")
        
    except Exception as e:
        logger.error(f"❌ Failed to compute awards: {e}")
        # Set empty awards
        ctx["awards"] = {"top_score": {"team": "", "points": ""}, "low_score": {"team": "", "points": ""}, "largest_gap": {"desc": "", "gap": ""}}
        ctx["AWARD_TOP_TEAM"] = ""
        ctx["AWARD_TOP_NOTE"] = ""
        ctx["AWARD_CUPCAKE_TEAM"] = ""
        ctx["AWARD_CUPCAKE_NOTE"] = ""
        ctx["AWARD_KITTY_TEAM"] = ""
        ctx["AWARD_KITTY_NOTE"] = ""
    
    # Attach logos using team_logos.json as source of truth
    try:
        logger.info("🖼️ Attaching team logos from team_logos.json...")
        _attach_team_logos(doc, games)
        ctx["GAMES"] = games
        ctx.setdefault("LEAGUE_LOGO_NAME", ctx.get("LEAGUE_NAME", "Gridiron Gazette"))
        _attach_special_logos(doc, ctx)
        _map_front_page_slots(ctx)
        logger.info("✅ Logos attached successfully")
    except Exception as e:
        logger.error(f"⚠️ Error attaching logos: {e}")
        # Continue without logos rather than failing completely
    
    # Handle output path with token substitution
    try:
        out_hint = Path(output_dir)
        league_name = (ctx.get("LEAGUE_NAME") or ctx.get("LEAGUE_LOGO_NAME") or "League").strip()
        
        # Build token map
        tokens = {
            "week": str(week),
            "week02": f"{week:02d}",
            "year": str(year),
            "league": league_name,
        }
        
        def fill_tokens(s: str) -> str:
            for k, v in tokens.items():
                s = s.replace("{" + k + "}", v)
            return s
        
        if out_hint.suffix.lower() == ".docx":
            out_path = Path(fill_tokens(str(out_hint)))
            out_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            d = out_hint
            d.mkdir(parents=True, exist_ok=True)
            out_path = d / f"gazette_week_{week}.docx"
        
        # ===== FINAL TEMPLATE RENDER =====
        logger.info("📄 Rendering final document...")
        
        # Log key template variables for debugging
        logger.info(f"Template variables summary:")
        logger.info(f"  LEAGUE_NAME: {ctx.get('LEAGUE_NAME', 'N/A')}")
        logger.info(f"  WEEK: {ctx.get('WEEK', 'N/A')}")
        logger.info(f"  Games count: {len(ctx.get('GAMES', []))}")
        logger.info(f"  MATCHUP1_HOME: {ctx.get('MATCHUP1_HOME', 'N/A')}")
        logger.info(f"  MATCHUP1_TOP_HOME: {ctx.get('MATCHUP1_TOP_HOME', 'N/A')}")
        logger.info(f"  AWARD_TOP_TEAM: {ctx.get('AWARD_TOP_TEAM', 'N/A')}")
        logger.info(f"  AWARD_CUPCAKE_TEAM: {ctx.get('AWARD_CUPCAKE_TEAM', 'N/A')}")
        
        doc.render(ctx)
        doc.save(out_path)
        
        # Verify file was created
        if out_path.exists():
            file_size = out_path.stat().st_size
            logger.info(f"✅ Weekly recap saved successfully!")
            logger.info(f"📄 File: {out_path}")
            logger.info(f"📊 Size: {file_size / 1024:.1f} KB")
        else:
            logger.error("❌ File was not created!")
        
        return str(out_path)
        
    except Exception as e:
        logger.error(f"❌ Error saving document: {e}")
        import traceback
        logger.error(f"Save error traceback: {traceback.format_exc()}")
        raise

# ===== DEBUGGING HELPERS =====

def debug_player_data(league, week, team_limit=2):
    """Debug function to inspect player data structure"""
    logger.info(f"🔍 DEBUGGING PLAYER DATA for week {week}")
    
    try:
        scoreboard = league.scoreboard(week)
        for i, matchup in enumerate(scoreboard[:team_limit]):
            logger.info(f"\n--- MATCHUP {i} DEBUG ---")
            
            for team_type in ['home_team', 'away_team']:
                team = getattr(matchup, team_type, None)
                if not team:
                    logger.warning(f"{team_type}: MISSING")
                    continue
                
                team_name = getattr(team, 'team_name', 'Unknown')
                logger.info(f"\n{team_type.upper()}: {team_name}")
                
                # Check for player attributes
                player_attrs = ['lineup', 'roster', 'starters', 'box_players']
                for attr in player_attrs:
                    if hasattr(team, attr):
                        players = getattr(team, attr)
                        logger.info(f"  {attr}: {len(players) if players else 0} players")
                        
                        # Sample first player
                        if players and len(players) > 0:
                            p = players[0]
                            logger.info(f"    Sample player: {get_player_name(p)}")
                            logger.info(f"      Points: {get_player_points(p)}")
                            logger.info(f"      Projected: {get_player_projected(p)}")
                            logger.info(f"      Is starter: {is_starter(p)}")
                            
                            # Show available attributes
                            attrs = [a for a in dir(p) if not a.startswith('_')][:10]
                            logger.info(f"      Available attrs: {attrs}")
                    else:
                        logger.info(f"  {attr}: NOT FOUND")
            
            if i >= team_limit - 1:
                break
                
    except Exception as e:
        logger.error(f"Debug failed: {e}")

def validate_template_context(ctx):
    """Validate that all expected template variables are present"""
    logger.info("🔍 TEMPLATE CONTEXT VALIDATION")
    
    required_vars = [
        'LEAGUE_NAME', 'WEEK', 'YEAR', 'GAMES',
        'MATCHUP1_HOME', 'MATCHUP1_AWAY', 'MATCHUP1_TOP_HOME', 'MATCHUP1_TOP_AWAY',
        'AWARD_TOP_TEAM', 'AWARD_CUPCAKE_TEAM', 'AWARD_KITTY_TEAM'
    ]
    
    missing_vars = []
    empty_vars = []
    
    for var in required_vars:
        if var not in ctx:
            missing_vars.append(var)
        elif not ctx[var]:
            empty_vars.append(var)
        else:
            logger.info(f"✅ {var}: {str(ctx[var])[:50]}")
    
    if missing_vars:
        logger.warning(f"❌ Missing variables: {missing_vars}")
    
    if empty_vars:
        logger.warning(f"⚠️ Empty variables: {empty_vars}")
    
    if not missing_vars and not empty_vars:
        logger.info("✅ All required template variables present and populated!")

if __name__ == "__main__":
    # Test/debug mode
    print("This is the complete fixed updated_weekly_recap.py")
    print("Key fixes implemented:")
    print("- Fixed stats assignment bug (force assignment instead of setdefault)")
    print("- Enhanced awards calculation from LLM text when API scores fail")
    print("- Improved team logo mapping from team_logos.json")
    print("- Comprehensive error handling and logging")
    print("- Multiple fallback methods for player data extraction")
    print("\nImport this module and use build_weekly_recap() function")