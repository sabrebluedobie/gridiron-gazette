#!/usr/bin/env python3
"""
Fixed build_gazette.py that properly integrates with your existing data pipeline
"""

import os
import json
import argparse
from pathlib import Path
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

# Import your existing robust data pipeline
from gazette_data import fetch_week_from_espn, build_context
from gazette_helpers import add_enumerated_matchups, add_template_synonyms
from mascots_util import logo_for

def get_openai_key():
    return os.getenv("OPENAI_API_KEY")

def get_espn_credentials():
    return {
        'espn_s2': os.getenv("ESPN_S2"),
        'swid': os.getenv("SWID")
    }

def load_league_config():
    """Load league configuration from leagues.json"""
    with open('leagues.json', 'r') as f:
        leagues = json.load(f)
    return leagues[0]  # Assuming single league for now

def generate_llm_content(games, style="mascot", words=1000, temperature=0.4):
    """Generate LLM content using your existing games structure"""
    if not get_openai_key():
        print("Warning: No OpenAI API key found, skipping LLM blurbs")
        return {}
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=get_openai_key())
    except ImportError:
        print("Warning: OpenAI library not available, skipping LLM blurbs")
        return {}
    
    llm_content = {}
    
    # Generate blurbs for each game
    for i, game in enumerate(games[:10], 1):  # Limit to 10 games
        home = game.get('home', '')
        away = game.get('away', '')
        hs = game.get('hs', '')
        as_score = game.get('as', '')
        
        if not home or not away:
            continue
            
        # Create contextual prompt based on actual game data
        if hs and as_score:
            try:
                hs_float = float(hs)
                as_float = float(as_score)
                score_context = f"The final score was {home} {hs} - {away} {as_score}. "
                if hs_float > as_float:
                    winner = home
                    loser = away
                else:
                    winner = away
                    loser = home
                score_context += f"{winner} defeated {loser}. "
            except (ValueError, TypeError):
                score_context = f"{home} faced off against {away}. "
        else:
            score_context = f"{home} faced off against {away}. "
        
        prompt = f"""Write a {words}-word {style}-style fantasy football recap for this matchup:

{score_context}

Style guidelines for '{style}' writing:
- If 'mascot': Use team mascot personalities and characteristics in the narrative
- If 'rtg': Use conversational, buddy-talk style like friends discussing the game
- If 'default': Standard sports journalism style

Keep it engaging but grounded in fantasy football reality. Focus on team performance, key plays, and what fantasy managers should know."""

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=int(words * 1.5),  # Give some buffer
                temperature=temperature
            )
            content = response.choices[0].message.content.strip()
            llm_content[f'MATCHUP{i}_BLURB'] = content
            print(f"Generated LLM blurb for {home} vs {away}")
        except Exception as e:
            print(f"Error generating LLM content for matchup {i} ({home} vs {away}): {e}")
            llm_content[f'MATCHUP{i}_BLURB'] = f"Exciting matchup between {home} and {away}!"
    
    return llm_content

def add_logo_images(context, doc, max_slots=10, width_mm=25):
    """Add team logo images to context using your existing logo system"""
    for i in range(1, max_slots + 1):
        home = context.get(f"MATCHUP{i}_HOME", "")
        away = context.get(f"MATCHUP{i}_AWAY", "")
        
        # Use your existing logo_for function
        home_logo_path = logo_for(home) if home else None
        away_logo_path = logo_for(away) if away else None
        
        if home_logo_path and Path(home_logo_path).exists():
            try:
                context[f"MATCHUP{i}_HOME_LOGO"] = InlineImage(doc, home_logo_path, width=Mm(width_mm))
                print(f"Added logo for {home}: {home_logo_path}")
            except Exception as e:
                print(f"Error loading logo for {home}: {e}")
                context[f"MATCHUP{i}_HOME_LOGO"] = "[no-logo]"
        else:
            context[f"MATCHUP{i}_HOME_LOGO"] = "[no-logo]"
            if home:
                print(f"No logo found for {home}")
        
        if away_logo_path and Path(away_logo_path).exists():
            try:
                context[f"MATCHUP{i}_AWAY_LOGO"] = InlineImage(doc, away_logo_path, width=Mm(width_mm))
                print(f"Added logo for {away}: {away_logo_path}")
            except Exception as e:
                print(f"Error loading logo for {away}: {e}")
                context[f"MATCHUP{i}_AWAY_LOGO"] = "[no-logo]"
        else:
            context[f"MATCHUP{i}_AWAY_LOGO"] = "[no-logo]"
            if away:
                print(f"No logo found for {away}")

def main():
    parser = argparse.ArgumentParser(description='Build fantasy football gazette')
    parser.add_argument('--template', required=True, help='Path to Word template')
    parser.add_argument('--out-docx', required=True, help='Output docx file path')
    parser.add_argument('--league-id', required=True, help='ESPN League ID')
    parser.add_argument('--year', type=int, required=True, help='League year')
    parser.add_argument('--week', type=int, default=1, help='Week number')
    parser.add_argument('--llm-blurbs', action='store_true', help='Generate LLM blurbs')
    parser.add_argument('--blurb-style', default='mascot', help='LLM blurb style')
    parser.add_argument('--blurb-words', type=int, default=1000, help='LLM blurb word count')
    parser.add_argument('--temperature', type=float, default=0.4, help='LLM temperature')
    parser.add_argument('--slots', type=int, default=10, help='Maximum number of matchup slots')
    
    args = parser.parse_args()
    
    # Load league configuration
    league_config = load_league_config()
    
    # Get ESPN credentials
    espn_creds = get_espn_credentials()
    if not espn_creds['espn_s2'] or not espn_creds['swid']:
        raise RuntimeError("ESPN_S2 and SWID environment variables are required")
    
    # Override config with passed parameters
    league_config['league_id'] = int(args.league_id)
    league_config['year'] = args.year
    league_config['week'] = args.week
    league_config['espn_s2'] = espn_creds['espn_s2']
    league_config['swid'] = espn_creds['swid']
    
    # Fetch ESPN data using your existing pipeline
    print(f"Fetching data for league {args.league_id}, week {args.week}...")
    games = fetch_week_from_espn(
        league_id=int(args.league_id),
        year=args.year,
        espn_s2=espn_creds['espn_s2'],
        swid=espn_creds['swid'],
        week=args.week
    )
    
    if not games:
        raise RuntimeError(f"No games found for week {args.week}. Check your ESPN credentials and league settings.")
    
    print(f"Found {len(games)} games for week {args.week}")
    for i, game in enumerate(games, 1):
        print(f"  Game {i}: {game.get('home', '?')} vs {game.get('away', '?')} - {game.get('hs', '?')} to {game.get('as', '?')}")
    
    # Build context using your existing system
    context = build_context(league_config, games)
    
    # Add enumerated matchups (MATCHUP1_HOME, etc.)
    add_enumerated_matchups(context, max_slots=args.slots)
    
    # Add template synonyms
    add_template_synonyms(context, slots=args.slots)
    
    # Generate LLM content if requested
    if args.llm_blurbs:
        print("Generating LLM content...")
        llm_content = generate_llm_content(
            games, 
            style=args.blurb_style, 
            words=args.blurb_words,
            temperature=args.temperature
        )
        context.update(llm_content)
    
    # Create output directory if it doesn't exist
    output_path = Path(args.out_docx)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Load template
    print(f"Loading template {args.template}...")
    if not Path(args.template).exists():
        raise FileNotFoundError(f"Template not found: {args.template}")
    
    doc = DocxTemplate(args.template)
    
    # Add team logos
    print("Processing team logos...")
    add_logo_images(context, doc, max_slots=args.slots)
    
    # Add league and sponsor logos if specified
    if league_config.get('league_logo'):
        league_logo_path = Path(league_config['league_logo'])
        if league_logo_path.exists():
            try:
                context['LEAGUE_LOGO'] = InlineImage(doc, str(league_logo_path), width=Mm(30))
                print(f"Added league logo: {league_logo_path}")
            except Exception as e:
                print(f"Error loading league logo: {e}")
    
    sponsor = league_config.get('sponsor', {})
    if sponsor.get('logo'):
        sponsor_logo_path = Path(sponsor['logo'])
        if sponsor_logo_path.exists():
            try:
                context['SPONSOR_LOGO'] = InlineImage(doc, str(sponsor_logo_path), width=Mm(25))
                print(f"Added sponsor logo: {sponsor_logo_path}")
            except Exception as e:
                print(f"Error loading sponsor logo: {e}")
    
    # Add other context fields
    context.update({
        'FOOTER_NOTE': sponsor.get('line', 'Fantasy Football Gazette'),
        'SPONSOR_LINE': sponsor.get('line', 'Your weekly fantasy fix'),
        'title': league_config.get('name', 'Fantasy Football Gazette'),
        'WEEK_NUMBER': args.week,
        'WEEKLY_INTRO': f"Week {args.week} recap for {league_config.get('name', 'your league')}",
    })
    
    # Debug: Print some context keys
    print("\nContext summary:")
    print(f"  Games: {len(context.get('games', []))}")
    print(f"  Template keys with MATCHUP: {len([k for k in context.keys() if 'MATCHUP' in k])}")
    print(f"  Logo keys: {len([k for k in context.keys() if 'LOGO' in k])}")
    
    # Check for undeclared template variables
    try:
        undeclared = doc.get_undeclared_template_variables(context)
        if undeclared:
            print(f"\nWarning: Template has undeclared variables: {sorted(undeclared)}")
    except Exception as e:
        print(f"Could not check template variables: {e}")
    
    # Render template
    print("Rendering template...")
    doc.render(context)
    
    # Save output
    doc.save(args.out_docx)
    print(f"Gazette saved to {args.out_docx}")

if __name__ == "__main__":
    main()