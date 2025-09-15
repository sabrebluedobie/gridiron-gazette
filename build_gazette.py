#!/usr/bin/env python3

import os
import json
import argparse
from pathlib import Path
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
import sys
import traceback

def get_openai_key():
    return os.getenv("OPENAI_API_KEY")

def get_espn_credentials():
    return {
        'espn_s2': os.getenv("ESPN_S2"),
        'swid': os.getenv("SWID")
    }

def load_league_config():
    """Load league configuration from leagues.json"""
    try:
        with open('leagues.json', 'r') as f:
            leagues = json.load(f)
        return leagues[0]  # Assuming single league for now
    except Exception as e:
        print(f"Error loading leagues.json: {e}")
        raise

def simple_logo_for(team_name):
    """Simple logo finder that works with the generated logos"""
    if not team_name:
        return None
    
    # Check team_logos.json first
    try:
        with open('team_logos.json', 'r') as f:
            logo_mapping = json.load(f)
        if team_name in logo_mapping:
            logo_path = logo_mapping[team_name]
            if Path(logo_path).exists():
                return logo_path
    except:
        pass
    
    # Look for files in logos directories
    import re
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', team_name)
    
    search_dirs = [
        'logos/generated_logos',
        'logos/ai', 
        'logos',
        'assets/logos'
    ]
    
    for search_dir in search_dirs:
        base_path = Path(search_dir)
        if not base_path.exists():
            continue
            
        # Try exact match first
        for ext in ['.png', '.jpg', '.jpeg', '.webp', '.txt']:
            candidate = base_path / f"{safe_name}{ext}"
            if candidate.exists():
                return str(candidate)
        
        # Try partial matches
        for file_path in base_path.glob("*"):
            if file_path.is_file() and safe_name.lower() in file_path.stem.lower():
                return str(file_path)
    
    return None

def fetch_espn_data(league_id, year, espn_s2, swid, week_number):
    """Fetch data from ESPN Fantasy API with better error handling"""
    print(f"Connecting to ESPN league {league_id} for week {week_number}")
    
    try:
        from espn_api.football import League
        
        league = League(
            league_id=league_id,
            year=year,
            espn_s2=espn_s2,
            swid=swid
        )
        
        print(f"✅ Connected to league: {league.settings.name}")
        print(f"Teams in league: {len(league.teams)}")
        
        # Log team names
        for i, team in enumerate(league.teams, 1):
            print(f"  {i}. {team.team_name} (Owner: {team.owner})")
        
        # Get matchups for the specified week
        matchups = league.scoreboard(week=week_number)
        print(f"Found {len(matchups)} matchups for week {week_number}")
        
        # Process matchups into template format
        matchup_data = {}
        for i, matchup in enumerate(matchups[:10], 1):  # Limit to 10 matchups
            try:
                home_team = matchup.home_team
                away_team = matchup.away_team
                
                home_name = home_team.team_name if home_team else "Unknown"
                away_name = away_team.team_name if away_team else "Unknown"
                home_score = getattr(matchup, 'home_score', 0) or 0
                away_score = getattr(matchup, 'away_score', 0) or 0
                
                print(f"  Game {i}: {home_name} ({home_score}) vs {away_name} ({away_score})")
                
                matchup_data.update({
                    f'MATCHUP{i}_HOME': home_name,
                    f'MATCHUP{i}_AWAY': away_name,
                    f'MATCHUP{i}_HS': home_score,
                    f'MATCHUP{i}_AS': away_score,
                })
                
                # Add logos
                home_logo = simple_logo_for(home_name)
                away_logo = simple_logo_for(away_name)
                
                if home_logo:
                    matchup_data[f'MATCHUP{i}_HOME_LOGO_PATH'] = home_logo
                    print(f"    Found logo for {home_name}: {home_logo}")
                else:
                    print(f"    No logo found for {home_name}")
                
                if away_logo:
                    matchup_data[f'MATCHUP{i}_AWAY_LOGO_PATH'] = away_logo
                    print(f"    Found logo for {away_name}: {away_logo}")
                else:
                    print(f"    No logo found for {away_name}")
                
            except Exception as e:
                print(f"Error processing matchup {i}: {e}")
                continue
        
        return matchup_data
        
    except Exception as e:
        print(f"❌ Error fetching ESPN data: {e}")
        traceback.print_exc()
        raise

def generate_llm_content(matchup_data, style="mascot", words=500, temperature=0.4):
    """Generate LLM content if requested"""
    openai_key = get_openai_key()
    if not openai_key:
        print("⚠️  No OpenAI API key found, skipping LLM blurbs")
        return {}
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
        print(f"Generating LLM blurbs in {style} style...")
    except ImportError:
        print("⚠️  OpenAI library not available, skipping LLM blurbs")
        return {}
    except Exception as e:
        print(f"⚠️  Error initializing OpenAI: {e}")
        return {}
    
    llm_content = {}
    
    # Generate blurbs for each matchup
    for i in range(1, 11):  # Up to 10 matchups
        home_key = f'MATCHUP{i}_HOME'
        away_key = f'MATCHUP{i}_AWAY'
        hs_key = f'MATCHUP{i}_HS'
        as_key = f'MATCHUP{i}_AS'
        
        if home_key not in matchup_data or away_key not in matchup_data:
            continue
        
        home = matchup_data[home_key]
        away = matchup_data[away_key]
        home_score = matchup_data.get(hs_key, 'TBD')
        away_score = matchup_data.get(as_key, 'TBD')
        
        # Create a contextual prompt
        if home_score != 'TBD' and away_score != 'TBD':
            try:
                hs_float = float(home_score)
                as_float = float(away_score)
                if hs_float > as_float:
                    winner, loser = home, away
                    winning_score, losing_score = hs_float, as_float
                else:
                    winner, loser = away, home
                    winning_score, losing_score = as_float, hs_float
                
                prompt = f"""Write a {words}-word fantasy football recap in {style} style for this matchup:

{winner} defeated {loser} with a final score of {winning_score:.1f} to {losing_score:.1f}.

Style notes:
- {style} style means {"use team mascot personalities and characteristics" if style == "mascot" else "conversational, buddy-talk style" if style == "rtg" else "standard sports journalism"}
- Focus on fantasy football implications
- Keep it engaging but realistic
- Mention key performances that led to the win"""
            except (ValueError, TypeError):
                prompt = f"Write a {words}-word {style}-style fantasy football preview for {home} vs {away}."
        else:
            prompt = f"Write a {words}-word {style}-style fantasy football preview for {home} vs {away}."
        
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=int(words * 1.5),
                temperature=temperature
            )
            content = response.choices[0].message.content.strip()
            llm_content[f'MATCHUP{i}_BLURB'] = content
            print(f"✅ Generated blurb for {home} vs {away}")
        except Exception as e:
            print(f"⚠️  Error generating LLM content for matchup {i}: {e}")
            llm_content[f'MATCHUP{i}_BLURB'] = f"Exciting matchup between {home} and {away}!"
    
    print(f"Generated {len(llm_content)} LLM blurbs")
    return llm_content

def create_image_objects(doc, context):
    """Convert image paths to InlineImage objects"""
    image_context = {}
    
    for key, value in context.items():
        if key.endswith('_LOGO_PATH') and value and Path(value).exists():
            # Convert path to InlineImage object
            logo_key = key.replace('_PATH', '')
            try:
                image_context[logo_key] = InlineImage(doc, value, width=Mm(25))
                print(f"✅ Loaded image for {logo_key}: {value}")
            except Exception as e:
                print(f"⚠️  Error loading image {value}: {e}")
                image_context[logo_key] = "[logo-error]"
        elif key in ['LEAGUE_LOGO', 'SPONSOR_LOGO']:
            # Handle league and sponsor logos
            if isinstance(value, str) and Path(value).exists():
                try:
                    image_context[key] = InlineImage(doc, value, width=Mm(30))
                    print(f"✅ Loaded {key}: {value}")
                except Exception as e:
                    print(f"⚠️  Error loading {key}: {e}")
        else:
            image_context[key] = value
    
    return image_context

def main():
    parser = argparse.ArgumentParser(description='Build fantasy football gazette')
    parser.add_argument('--template', required=True, help='Path to Word template')
    parser.add_argument('--out-docx', required=True, help='Output docx file path')
    parser.add_argument('--league-id', required=True, help='ESPN League ID')
    parser.add_argument('--year', type=int, required=True, help='League year')
    parser.add_argument('--week', type=int, default=1, help='Week number')
    parser.add_argument('--llm-blurbs', action='store_true', help='Generate LLM blurbs')
    parser.add_argument('--blurb-style', default='mascot', help='LLM blurb style')
    parser.add_argument('--blurb-words', type=int, default=500, help='LLM blurb word count')
    parser.add_argument('--temperature', type=float, default=0.4, help='LLM temperature')
    parser.add_argument('--slots', type=int, default=10, help='Max matchup slots')
    
    args = parser.parse_args()
    
    print(f"=== Building Gridiron Gazette ===")
    print(f"Template: {args.template}")
    print(f"Output: {args.out_docx}")
    print(f"League ID: {args.league_id}")
    print(f"Year: {args.year}")
    print(f"Week: {args.week}")
    print(f"LLM Blurbs: {args.llm_blurbs}")
    print()
    
    try:
        # Validate template exists
        if not Path(args.template).exists():
            raise FileNotFoundError(f"Template not found: {args.template}")
        
        # Load league configuration
        league_config = load_league_config()
        print(f"Loaded league config: {league_config.get('name', 'Unknown')}")
        
        # Get ESPN credentials
        espn_creds = get_espn_credentials()
        if not espn_creds['espn_s2'] or not espn_creds['swid']:
            raise RuntimeError("ESPN_S2 and SWID environment variables are required")
        
        # Fetch ESPN data
        espn_data = fetch_espn_data(
            league_id=int(args.league_id),
            year=args.year,
            espn_s2=espn_creds['espn_s2'],
            swid=espn_creds['swid'],
            week_number=args.week
        )
        
        if not espn_data:
            raise RuntimeError(f"No ESPN data found for week {args.week}")
        
        # Generate LLM content if requested
        llm_content = {}
        if args.llm_blurbs:
            llm_content = generate_llm_content(
                espn_data, 
                style=args.blurb_style, 
                words=args.blurb_words,
                temperature=args.temperature
            )
        
        # Build template context
        context = {
            'title': league_config.get('name', 'Fantasy Football Gazette'),
            'WEEK_NUMBER': args.week,
            'WEEKLY_INTRO': f"Week {args.week} recap for {league_config.get('name')}",
            'FOOTER_NOTE': league_config.get('sponsor', {}).get('line', 'Fantasy Football Gazette'),
            'SPONSOR_LINE': league_config.get('sponsor', {}).get('line', 'Your weekly fantasy fix'),
            **espn_data,
            **llm_content
        }
        
        # Add league and sponsor logos if they exist
        if league_config.get('league_logo'):
            league_logo_path = Path(league_config['league_logo'])
            if league_logo_path.exists():
                context['LEAGUE_LOGO'] = str(league_logo_path)
        
        sponsor = league_config.get('sponsor', {})
        if sponsor.get('logo'):
            sponsor_logo_path = Path(sponsor['logo'])
            if sponsor_logo_path.exists():
                context['SPONSOR_LOGO'] = str(sponsor_logo_path)
        
        # Create output directory if it doesn't exist
        output_path = Path(args.out_docx)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load and render template
        print(f"Loading template: {args.template}")
        doc = DocxTemplate(args.template)
        
        # Convert image paths to InlineImage objects
        print("Processing images...")
        context = create_image_objects(doc, context)
        
        # Debug: Print context summary
        print(f"\nContext summary:")
        print(f"  Total keys: {len(context)}")
        print(f"  Matchup keys: {len([k for k in context.keys() if 'MATCHUP' in k])}")
        print(f"  Logo keys: {len([k for k in context.keys() if 'LOGO' in k])}")
        
        # Check for undeclared template variables
        try:
            undeclared = doc.get_undeclared_template_variables(context)
            if undeclared:
                print(f"⚠️  Template has undeclared variables: {sorted(undeclared)[:10]}...")
            else:
                print("✅ All template variables are declared")
        except Exception as e:
            print(f"Could not check template variables: {e}")
        
        # Render template
        print("Rendering template...")
        doc.render(context)
        
        # Save output
        print(f"Saving to: {args.out_docx}")
        doc.save(args.out_docx)
        
        # Verify file was created
        if Path(args.out_docx).exists():
            file_size = Path(args.out_docx).stat().st_size
            print(f"✅ Gazette saved successfully!")
            print(f"   File: {args.out_docx}")
            print(f"   Size: {file_size:,} bytes")
        else:
            raise RuntimeError("File was not created!")
            
    except Exception as e:
        print(f"❌ Error building gazette: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()