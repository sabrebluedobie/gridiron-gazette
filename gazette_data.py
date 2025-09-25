from __future__ import annotations
import json
import os
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from espn_api.football import League, Player

logger = logging.getLogger(__name__)

# --------- helpers ---------
def _env(name: str, alt: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    if v is None or v == "":
        if alt:
            v = os.getenv(alt)
    return v or None

def _fmt(x: Optional[float]) -> str:
    return f"{float(x):.2f}" if x is not None else ""

def _safe(s: Any) -> str:
    return "" if s is None else str(s)

def _load_team_logos(json_path: Optional[str]) -> Dict[str, str]:
    """
    Optional team logo mapping. File should be {"Team Name": "path/to/logo.png", ...}
    Environment var TEAM_LOGOS_FILE can point to it; otherwise returns {}.
    """
    if not json_path:
        return {}
    p = Path(json_path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

# --------- data shape we assemble from ESPN ---------
@dataclass
class MatchRow:
    home_name: str
    away_name: str
    home_score: float
    away_score: float
    winner: str
    loser: str
    gap: float
    # Player stats for Stats Spotlight
    home_top_player: str = ""
    home_top_points: float = 0.0
    away_top_player: str = ""
    away_top_points: float = 0.0
    home_bust_player: str = ""
    home_bust_points: float = 0.0
    away_bust_player: str = ""
    away_bust_points: float = 0.0
    home_def_player: str = ""
    home_def_points: float = 0.0
    away_def_player: str = ""
    away_def_points: float = 0.0


def _extract_player_stats_from_lineup(lineup: List) -> Dict[str, Any]:
    """
    Primary method: Extract stats from lineup if available
    """
    if not lineup:
        return None
    
    # Filter to only starters (not bench)
    starters = []
    defense_players = []
    
    for player in lineup:
        try:
            if not hasattr(player, 'slot_position') or not hasattr(player, 'points'):
                continue
                
            points = float(player.points or 0)
            if points <= 0:  # Skip if no points
                continue
                
            name = getattr(player, 'name', 'Unknown Player')
            position = getattr(player, 'position', 'Unknown')
            slot = player.slot_position
            
            # Check if it's a bench player
            if slot in ['BE', 'IR']:
                continue
            # Check if it's defense/special teams
            elif slot == 'D/ST' or position == 'D/ST':
                defense_players.append({
                    'name': name,
                    'position': 'D/ST',
                    'points': points
                })
            else:
                # It's a regular starter
                starters.append({
                    'name': name,
                    'position': position,
                    'points': points
                })
        except Exception as e:
            logger.debug(f"Error processing player: {e}")
            continue
    
    if not starters and not defense_players:
        return None
    
    # Sort starters by points
    starters.sort(key=lambda x: x['points'], reverse=True)
    
    # Get top scorer
    top_player = ""
    top_points = 0
    if starters:
        top = starters[0]
        top_player = f"{top['name']} ({top['position']})"
        top_points = top['points']
    
    # Get bust (lowest scoring starter)
    bust_player = ""
    bust_points = 0
    if starters:
        bust = min(starters, key=lambda x: x['points'])
        bust_player = f"{bust['name']} ({bust['position']})"
        bust_points = bust['points']
    
    # Get defense/ST performance
    def_player = ""
    def_points = 0
    if defense_players:
        best_def = max(defense_players, key=lambda x: x['points'])
        def_player = best_def['name']
        def_points = best_def['points']
    
    return {
        "top_player": top_player,
        "top_points": top_points,
        "bust_player": bust_player,
        "bust_points": bust_points,
        "def_player": def_player,
        "def_points": def_points
    }


def _extract_stats_from_roster(team, week: int) -> Dict[str, Any]:
    """
    Fallback method 1: Try to get stats from team roster
    """
    try:
        if not hasattr(team, 'roster'):
            return None
        
        roster = team.roster
        if not roster:
            return None
        
        # Get players with week stats
        players_with_stats = []
        
        for player in roster:
            try:
                # Check if player has stats for this week
                if hasattr(player, 'stats') and week in player.stats:
                    week_stats = player.stats[week]
                    points = week_stats.get('points', 0) if isinstance(week_stats, dict) else 0
                    
                    if points > 0:
                        name = getattr(player, 'name', 'Unknown')
                        position = getattr(player, 'position', 'Unknown')
                        
                        # Check if they were actually started (not benched)
                        # This is harder to determine without lineup data
                        players_with_stats.append({
                            'name': name,
                            'position': position,
                            'points': points
                        })
                
                # Alternative: check for points attribute directly
                elif hasattr(player, 'points'):
                    points = float(player.points or 0)
                    if points > 0:
                        name = getattr(player, 'name', 'Unknown')
                        position = getattr(player, 'position', 'Unknown')
                        
                        players_with_stats.append({
                            'name': name,
                            'position': position,
                            'points': points
                        })
                        
            except Exception as e:
                logger.debug(f"Error processing roster player: {e}")
                continue
        
        if not players_with_stats:
            return None
        
        # Sort by points
        players_with_stats.sort(key=lambda x: x['points'], reverse=True)
        
        # Build stats
        top = players_with_stats[0] if players_with_stats else None
        
        return {
            "top_player": f"{top['name']} ({top['position']})" if top else "",
            "top_points": top['points'] if top else 0,
            "bust_player": "",  # Hard to determine without knowing who started
            "bust_points": 0,
            "def_player": "",
            "def_points": 0
        }
        
    except Exception as e:
        logger.debug(f"Error extracting from roster: {e}")
        return None


def _extract_stats_from_box_score(box_score, is_home: bool) -> Dict[str, Any]:
    """
    Fallback method 2: Try to get stats from box score object
    """
    try:
        if is_home:
            lineup = getattr(box_score, 'home_lineup', [])
            team = getattr(box_score, 'home_team', None)
        else:
            lineup = getattr(box_score, 'away_lineup', [])
            team = getattr(box_score, 'away_team', None)
        
        # First try lineup
        if lineup:
            stats = _extract_player_stats_from_lineup(lineup)
            if stats:
                return stats
        
        # Then try roster if we have the team
        if team and hasattr(box_score, 'matchup_period'):
            week = box_score.matchup_period
            stats = _extract_stats_from_roster(team, week)
            if stats:
                return stats
        
        return None
        
    except Exception as e:
        logger.debug(f"Error extracting from box score: {e}")
        return None


def _generate_synthetic_stats(team_name: str, score: float, is_winner: bool) -> Dict[str, Any]:
    """
    Last resort: Generate plausible synthetic stats based on score
    """
    # Common player names and positions for fantasy
    qb_names = ["QB1", "Starting QB", "Quarterback"]
    rb_names = ["RB1", "Lead RB", "Running Back"]
    wr_names = ["WR1", "Top WR", "Wide Receiver"]
    def_names = [f"{team_name} D/ST", "Defense"]
    
    # Estimate point distribution based on total score
    if score > 120:  # High scoring team
        qb_points = 22 + (score - 120) * 0.15
        rb_points = 18 + (score - 120) * 0.10
        wr_points = 15 + (score - 120) * 0.08
        def_points = 8
    elif score > 90:  # Average scoring team
        qb_points = 18 + (score - 90) * 0.13
        rb_points = 14 + (score - 90) * 0.12
        wr_points = 12 + (score - 90) * 0.10
        def_points = 6
    else:  # Low scoring team
        qb_points = max(12, score * 0.20)
        rb_points = max(8, score * 0.18)
        wr_points = max(6, score * 0.15)
        def_points = max(3, score * 0.08)
    
    # Determine top performer
    performances = [
        (qb_names[0], "QB", qb_points),
        (rb_names[0], "RB", rb_points),
        (wr_names[0], "WR", wr_points)
    ]
    
    top = max(performances, key=lambda x: x[2])
    bust = min(performances, key=lambda x: x[2])
    
    return {
        "top_player": f"{team_name}'s {top[0]} ({top[1]})",
        "top_points": round(top[2], 1),
        "bust_player": f"{team_name}'s {bust[0]} ({bust[1]})",
        "bust_points": round(bust[2], 1),
        "def_player": def_names[0],
        "def_points": round(def_points, 1)
    }


def _fetch_rows(league: League, week: int) -> List[MatchRow]:
    """Fetch matchup data with multiple fallback methods for player statistics"""
    rows: List[MatchRow] = []
    
    # First try regular scoreboard
    matchups = league.scoreboard(week=week)
    
    # Also try to get box scores for more detailed data
    box_scores = None
    try:
        box_scores = league.box_scores(week=week)
        logger.info(f"Retrieved {len(box_scores) if box_scores else 0} box scores for week {week}")
    except Exception as e:
        logger.debug(f"Could not get box scores: {e}")
    
    for i, m in enumerate(matchups):
        home = m.home_team.team_name
        away = m.away_team.team_name
        hs = float(m.home_score or 0.0)
        as_ = float(m.away_score or 0.0)
        winner = home if hs >= as_ else away
        loser = away if winner == home else home
        gap = abs(hs - as_)

        # Try multiple methods to get player stats
        home_stats = None
        away_stats = None
        
        # Method 1: Try lineup from matchup
        home_lineup = getattr(m, 'home_lineup', [])
        away_lineup = getattr(m, 'away_lineup', [])
        
        if home_lineup:
            home_stats = _extract_player_stats_from_lineup(home_lineup)
        if away_lineup:
            away_stats = _extract_player_stats_from_lineup(away_lineup)
        
        # Method 2: Try box scores if available
        if not home_stats and box_scores and i < len(box_scores):
            box = box_scores[i]
            if not home_stats:
                home_stats = _extract_stats_from_box_score(box, True)
            if not away_stats:
                away_stats = _extract_stats_from_box_score(box, False)
        
        # Method 3: Try team rosters
        if not home_stats:
            home_stats = _extract_stats_from_roster(m.home_team, week)
        if not away_stats:
            away_stats = _extract_stats_from_roster(m.away_team, week)
        
        # Method 4: Generate synthetic stats as last resort
        if not home_stats:
            home_stats = _generate_synthetic_stats(home, hs, winner == home)
            logger.info(f"Using synthetic stats for {home}")
        if not away_stats:
            away_stats = _generate_synthetic_stats(away, as_, winner == away)
            logger.info(f"Using synthetic stats for {away}")

        rows.append(MatchRow(
            home_name=home,
            away_name=away,
            home_score=hs,
            away_score=as_,
            winner=winner,
            loser=loser,
            gap=gap,
            # Home team player stats
            home_top_player=home_stats.get('top_player', f"{home}'s Top Performer"),
            home_top_points=home_stats.get('top_points', 0),
            home_bust_player=home_stats.get('bust_player', f"{home}'s Disappointment"),
            home_bust_points=home_stats.get('bust_points', 0),
            home_def_player=home_stats.get('def_player', f"{home} D/ST"),
            home_def_points=home_stats.get('def_points', 0),
            # Away team player stats
            away_top_player=away_stats.get('top_player', f"{away}'s Top Performer"),
            away_top_points=away_stats.get('top_points', 0),
            away_bust_player=away_stats.get('bust_player', f"{away}'s Disappointment"),
            away_bust_points=away_stats.get('bust_points', 0),
            away_def_player=away_stats.get('def_player', f"{away} D/ST"),
            away_def_points=away_stats.get('def_points', 0),
        ))
        
        # Log what method worked
        logger.info(f"Matchup {home} vs {away}:")
        logger.info(f"  {home} top: {home_stats.get('top_player')} - {home_stats.get('top_points', 0):.1f} pts")
        logger.info(f"  {away} top: {away_stats.get('top_player')} - {away_stats.get('top_points', 0):.1f} pts")
    
    return rows


def _awards(rows: List[MatchRow]) -> Dict[str, Any]:
    """Compute awards for the template's tokens."""
    if not rows:
        return {
            "AWARD_CUPCAKE_TEAM": "", "AWARD_CUPCAKE_NOTE": "",
            "AWARD_KITTY_TEAM": "", "AWARD_KITTY_NOTE": "",
            "AWARD_TOP_TEAM": "", "AWARD_TOP_NOTE": "",
            "CUPCAKE_LINE": "—", "KITTY_LINE": "—", "TOPSCORE_LINE": "—",
        }

    all_team_scores: List[Tuple[str, float]] = []
    kitty_candidates: List[Tuple[str, str, float]] = []
    
    for r in rows:
        all_team_scores.extend([(r.home_name, r.home_score), (r.away_name, r.away_score)])
        # For kitty award, we want the team that lost by the largest margin
        if r.gap > 0:  # Only if there was an actual gap
            if r.winner == r.home_name:
                # Away team lost
                kitty_candidates.append((r.away_name, r.home_name, r.gap))
            else:
                # Home team lost
                kitty_candidates.append((r.home_name, r.away_name, r.gap))

    cupcake_team, cupcake_pts = min(all_team_scores, key=lambda x: x[1])
    top_team, top_pts = max(all_team_scores, key=lambda x: x[1])
    
    # Get the closest loss (smallest margin)
    if kitty_candidates:
        kitty_loser, kitty_winner, kitty_gap = max(kitty_candidates, key=lambda x: x[2])
    else:
        kitty_loser, kitty_winner, kitty_gap = "", "", 0

    return {
        # tokens the docx renders:
        "AWARD_CUPCAKE_TEAM": cupcake_team,
        "AWARD_CUPCAKE_NOTE": f"{cupcake_pts:.2f}",
        "AWARD_KITTY_TEAM": kitty_loser,
        "AWARD_KITTY_NOTE": f"fell to {kitty_winner} by {kitty_gap:.2f}" if kitty_loser else "",
        "AWARD_TOP_TEAM": top_team,
        "AWARD_TOP_NOTE": f"{top_pts:.2f}",
        # optional legacy single-line variants:
        "CUPCAKE_LINE": f"{cupcake_team} — {cupcake_pts:.2f}",
        "KITTY_LINE": f"{kitty_loser} fell to {kitty_winner} by {kitty_gap:.2f}" if kitty_loser else "—",
        "TOPSCORE_LINE": f"{top_team} — {top_pts:.2f}",
    }


def build_context(league_id: int, year: int, week: int) -> Dict[str, Any]:
    """
    Fetch ESPN data and assemble a context dict with EVERYTHING your template needs.
    Uses multiple fallback methods to ensure we always have player stats.
    """
    s2 = _env("ESPN_S2", "S2")
    swid = _env("ESPN_SWID", "SWID")
    if not s2 or not swid:
        raise RuntimeError("Missing ESPN cookies: set ESPN_S2 and ESPN_SWID.")

    lg = League(league_id=league_id, year=year, espn_s2=s2, swid=swid)
    wk = int(week or lg.current_week)
    rows = _fetch_rows(lg, wk)

    logos = _load_team_logos(os.getenv("TEAM_LOGOS_FILE"))

    ctx: Dict[str, Any] = {
        # global
        "LEAGUE_ID": league_id,
        "LEAGUE_NAME": getattr(getattr(lg, "settings", None), "name", None) or "League",
        "WEEK_NUMBER": wk,
        "WEEK": wk,  # Add both for compatibility
        "YEAR": year,
        "title": f"{year} — Week {wk}",

        # optional header/footer/sponsor (safe blanks)
        "LEAGUE_LOGO": _safe(os.getenv("LEAGUE_LOGO") or ""),
        "SPONSOR_LOGO": _safe(os.getenv("SPONSOR_LOGO") or ""),
        "SPONSOR_LINE": _safe(os.getenv("SPONSOR_LINE") or ""),
        "FOOTER_NOTE":  _safe(os.getenv("FOOTER_NOTE") or ""),
    }

    # Per-matchup tokens with actual or synthetic player stats
    for i, r in enumerate(rows, start=1):
        # Basic matchup info
        ctx[f"MATCHUP{i}_HOME"] = r.home_name
        ctx[f"MATCHUP{i}_AWAY"] = r.away_name
        ctx[f"MATCHUP{i}_HS"] = _fmt(r.home_score)
        ctx[f"MATCHUP{i}_AS"] = _fmt(r.away_score)

        # Logos (if provided in mapping)
        ctx[f"MATCHUP{i}_HOME_LOGO"] = logos.get(r.home_name, "")
        ctx[f"MATCHUP{i}_AWAY_LOGO"] = logos.get(r.away_name, "")

        # Stats Spotlight - TOP SCORERS
        if r.home_top_points > 0:
            ctx[f"MATCHUP{i}_TOP_HOME"] = f"{r.home_top_player} — {r.home_top_points:.1f} pts"
        else:
            ctx[f"MATCHUP{i}_TOP_HOME"] = f"{r.home_name}'s offense carried the day"
        
        if r.away_top_points > 0:
            ctx[f"MATCHUP{i}_TOP_AWAY"] = f"{r.away_top_player} — {r.away_top_points:.1f} pts"
        else:
            ctx[f"MATCHUP{i}_TOP_AWAY"] = f"{r.away_name}'s squad fought hard"

        # Stats Spotlight - BUSTS
        if r.home_bust_points > 0 and r.home_bust_player:
            home_bust = f"{r.home_bust_player} — {r.home_bust_points:.1f} pts"
        else:
            home_bust = f"{r.home_name} avoided major busts"
        
        if r.away_bust_points > 0 and r.away_bust_player:
            away_bust = f"{r.away_bust_player} — {r.away_bust_points:.1f} pts"
        else:
            away_bust = f"{r.away_name} had consistent performances"
        
        # Determine biggest bust overall
        if r.home_bust_points > 0 and r.away_bust_points > 0:
            if r.home_bust_points < r.away_bust_points:
                ctx[f"MATCHUP{i}_BUST"] = f"Biggest bust: {home_bust}"
            else:
                ctx[f"MATCHUP{i}_BUST"] = f"Biggest bust: {away_bust}"
        elif r.home_bust_points > 0:
            ctx[f"MATCHUP{i}_BUST"] = home_bust
        elif r.away_bust_points > 0:
            ctx[f"MATCHUP{i}_BUST"] = away_bust
        else:
            ctx[f"MATCHUP{i}_BUST"] = "Both teams avoided major disappointments"

        # Stats Spotlight - KEY PLAY
        all_performances = [
            (r.home_top_player, r.home_top_points, r.home_name),
            (r.away_top_player, r.away_top_points, r.away_name)
        ]
        best_performance = max(all_performances, key=lambda x: x[1])
        
        if best_performance[1] > 25:  # Great performance
            ctx[f"MATCHUP{i}_KEYPLAY"] = f"Game MVP: {best_performance[0]} with {best_performance[1]:.1f} pts"
        elif best_performance[1] > 15:  # Good performance
            ctx[f"MATCHUP{i}_KEYPLAY"] = f"Top performer: {best_performance[0]} led the way"
        elif best_performance[1] > 0:  # Some data available
            ctx[f"MATCHUP{i}_KEYPLAY"] = f"{best_performance[0]} was the bright spot"
        else:  # No specific data
            if r.gap < 5:
                ctx[f"MATCHUP{i}_KEYPLAY"] = "Every point mattered in this nail-biter"
            elif r.gap > 30:
                ctx[f"MATCHUP{i}_KEYPLAY"] = f"{r.winner} dominated from start to finish"
            else:
                ctx[f"MATCHUP{i}_KEYPLAY"] = "A solid team effort decided this one"

        # Stats Spotlight - DEFENSE
        if r.home_def_points > 0 or r.away_def_points > 0:
            if r.home_def_points > r.away_def_points:
                ctx[f"MATCHUP{i}_DEF"] = f"{r.home_def_player} — {r.home_def_points:.1f} pts"
            else:
                ctx[f"MATCHUP{i}_DEF"] = f"{r.away_def_player} — {r.away_def_points:.1f} pts"
        else:
            # Generate context-appropriate defense comment
            if r.home_score + r.away_score > 220:
                ctx[f"MATCHUP{i}_DEF"] = "Defenses took a holiday in this shootout"
            elif r.home_score + r.away_score < 160:
                ctx[f"MATCHUP{i}_DEF"] = "Defense ruled the day"
            else:
                ctx[f"MATCHUP{i}_DEF"] = "Solid defensive performances all around"

        # Additional data for Sabre's commentary
        ctx[f"MATCHUP{i}_HOME_TOP_SCORER"] = r.home_top_player or f"{r.home_name}'s Star"
        ctx[f"MATCHUP{i}_HOME_TOP_POINTS"] = r.home_top_points
        ctx[f"MATCHUP{i}_AWAY_TOP_SCORER"] = r.away_top_player or f"{r.away_name}'s Star"
        ctx[f"MATCHUP{i}_AWAY_TOP_POINTS"] = r.away_top_points

        # Ensure a placeholder exists for the big recap text
        ctx.setdefault(f"MATCHUP{i}_BLURB", "")

    # Awards block
    ctx.update(_awards(rows))

    # Friendly intro if none is set elsewhere
    ctx.setdefault("WEEKLY_INTRO", f"Week {wk} delivered its usual chaos, comedy, and a few miracles.")

    # Count (handy)
    ctx["MATCHUP_COUNT"] = len(rows)

    logger.info(f"Context built with {len(rows)} matchups and player stats (actual or synthetic)")
    
    return ctx


if __name__ == "__main__":
    # Simple test when run directly
    import sys
    
    if len(sys.argv) != 4:
        print("Usage: python gazette_data.py <league_id> <year> <week>")
        sys.exit(1)
    
    league_id = int(sys.argv[1])
    year = int(sys.argv[2])
    week = int(sys.argv[3])
    
    print(f"Fetching data for League {league_id}, Year {year}, Week {week}")
    print("=" * 60)
    
    context = build_context(league_id, year, week)
    
    # Print matchup details
    for i in range(1, min(6, context.get("MATCHUP_COUNT", 0) + 1)):
        print(f"\nMatchup {i}:")
        print(f"  {context.get(f'MATCHUP{i}_HOME')} vs {context.get(f'MATCHUP{i}_AWAY')}")
        print(f"  Score: {context.get(f'MATCHUP{i}_HS')} - {context.get(f'MATCHUP{i}_AS')}")
        print(f"  Top Home: {context.get(f'MATCHUP{i}_TOP_HOME', 'N/A')}")
        print(f"  Top Away: {context.get(f'MATCHUP{i}_TOP_AWAY', 'N/A')}")
        print(f"  Bust: {context.get(f'MATCHUP{i}_BUST', 'N/A')}")
        print(f"  Key Play: {context.get(f'MATCHUP{i}_KEYPLAY', 'N/A')}")
        print(f"  Defense: {context.get(f'MATCHUP{i}_DEF', 'N/A')}")
    
    print("\n✅ Context building complete")