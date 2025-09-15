import os
import json
import argparse
from pathlib import Path
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Inches
from espn_api.football import League

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

from functools import lru_cache
import re
from pathlib import Path

def _normalize_name(s: str) -> str:
    """
    Normalize team names and filenames for matching:
    - lowercase
    - strip non-alphanumerics
    - collapse spaces
    """
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

@lru_cache(maxsize=1)
def _build_logo_index(root="logos/team_logos"):
    """
    Scan logos/team_logos and build a map of normalized_name -> file path.
    Supports png/jpg/jpeg/webp.
    """
    root_path = Path(root)
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    index = {}
    if root_path.exists():
        for p in root_path.rglob("*"):
            if p.is_file() and p.suffix.lower() in exts:
                key = _normalize_name(p.stem)
                index[key] = str(p)
    return index

def get_team_logo_path(team_name):
    """
    Fuzzy match an ESPN team name to a file in logos/team_logos/.
    Falls back to a default only if nothing matches.
    """
    index = _build_logo_index()
    if not team_name:
        return "logos/default_team_logo.png"

    norm = _normalize_name(team_name)

    # Direct match
    if norm in index:
        return index[norm]

    # Try without trailing 's' (e.g., "pumas" -> "puma")
    if norm.endswith("s") and norm[:-1] in index:
        return index[norm[:-1]]

    # Try progressively removing short tokens
    parts = norm.split()
    while len(parts) > 1:
        parts.pop()  # drop last token
        candidate = " ".join(parts)
        if candidate in index:
            return index[candidate]

    # Last resort: startswith/contains style scan
    for k, v in index.items():
        if norm in k or k in norm:
            return v

    return "logos/default_team_logo.png"

def fetch_espn_data(league_id, year, espn_s2, swid, week_number):
    """Fetch data from ESPN Fantasy API"""
    league = League(
        league_id=league_id,
        year=year,
        espn_s2=espn_s2,
        swid=swid
    )
    
    # Get matchups for the specified week
    matchups = league.scoreboard(week_number)
    
    # Process matchups into template format
    matchup_data = {}
    for i, matchup in enumerate(matchups[:6], 1):  # Limit to 6 matchups
        home_team = matchup.home_team
        away_team = matchup.away_team
        
        matchup_data.update({
            f'MATCHUP{i}_HOME': home_team.team_name,
            f'MATCHUP{i}_AWAY': away_team.team_name,
            f'MATCHUP{i}_HS': matchup.home_score,
            f'MATCHUP{i}_AS': matchup.away_score,
            f'MATCHUP{i}_HOME_LOGO_PATH': get_team_logo_path(home_team.team_name),
            f'MATCHUP{i}_AWAY_LOGO_PATH': get_team_logo_path(away_team.team_name),
            # Add more fields as needed for your template
        })
    
    return matchup_data

def generate_llm_content(matchup_data, style="mascot", words=1000):
    """Generate LLM content if requested"""
    if not get_openai_key():
        return {}
    
    # Import OpenAI here so it's only required when needed
    from openai import OpenAI
    
    client = OpenAI(api_key=get_openai_key())
    
    llm_content = {}
    
    # Generate blurbs for each matchup
    for i in range(1, 7):  # Assuming 6 matchups
        home_key = f'MATCHUP{i}_HOME'
        away_key = f'MATCHUP{i}_AWAY'
        
        if home_key in matchup_data:
            prompt = f"Write a {words}-word {style}-style recap blurb for a fantasy football matchup between {matchup_data[home_key]} and {matchup_data[away_key]}."
            
            try:
                response = client.chat.completions.create(
                    model="gpt-4.1-mini-2025-04-14",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=words + 100,
                    temperature=0.4
                )
                llm_content[f'MATCHUP{i}_BLURB'] = response.choices[0].message.content
            except Exception as e:
                print(f"Error generating LLM content for matchup {i}: {e}")
                llm_content[f'MATCHUP{i}_BLURB'] = f"Recap for {matchup_data[home_key]} vs {matchup_data[away_key]}"
    
    return llm_content

def create_image_objects(doc, context):
    """Convert image paths to InlineImage objects"""
    image_context = {}
    
    for key, value in context.items():
        if key.endswith('_LOGO_PATH') and os.path.exists(value):
            # Convert path to InlineImage object
            logo_key = key.replace('_PATH', '')
            try:
                image_context[logo_key] = InlineImage(doc, value, width=Inches(0.5))
            except Exception as e:
                print(f"Error loading image {value}: {e}")
                # Skip this logo if it fails to load
        elif key in ['LEAGUE_LOGO', 'SPONSOR_LOGO']:
            # Handle league and sponsor logos
            if isinstance(value, str) and os.path.exists(value):
                try:
                    image_context[key] = InlineImage(doc, value, width=Inches(1.0))
                except Exception as e:
                    print(f"Error loading {key}: {e}")
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
    parser.add_argument('--blurb-words', type=int, default=1000, help='LLM blurb word count')
    parser.add_argument('--temperature', type=float, default=0.4, help='LLM temperature')
    
    args = parser.parse_args()
    
    # Validate API key requirement
    if args.llm_blurbs and not get_openai_key():
        raise RuntimeError("OPENAI_API_KEY not set, but --llm-blurbs was requested.")
    
    # Load league configuration
    league_config = load_league_config()
    
    # Get ESPN credentials
    espn_creds = get_espn_credentials()
    if not espn_creds['espn_s2'] or not espn_creds['swid']:
        raise RuntimeError("ESPN_S2 and SWID environment variables are required")
    
    # Fetch ESPN data
    print(f"Fetching data for league {args.league_id}, week {args.week}...")
    espn_data = fetch_espn_data(
        league_id=int(args.league_id),
        year=args.year,
        espn_s2=espn_creds['espn_s2'],
        swid=espn_creds['swid'],
        week_number=args.week
    )
    
    # Generate LLM content if requested
    llm_content = {}
    if args.llm_blurbs:
        print("Generating LLM content...")
        llm_content = generate_llm_content(
            espn_data, 
            style=args.blurb_style, 
            words=args.blurb_words
        )
    
    # Build template context
    context = {
        'title': league_config.get('name', 'Fantasy Football Gazette'),
        'WEEK_NUMBER': args.week,
        'WEEKLY_INTRO': f"Week {args.week} recap for {league_config.get('name')}",
        'LEAGUE_LOGO': league_config.get('league_logo'),
        'SPONSOR_LOGO': league_config.get('sponsor', {}).get('logo'),
        'FOOTER_NOTE': league_config.get('sponsor', {}).get('line', 'Fantasy Football Gazette'),
        'SPONSOR_LINE': league_config.get('sponsor', {}).get('line', 'Your Sponsor Here'),
        **espn_data,
        **llm_content
    }
    
    # Create output directory if it doesn't exist
    output_path = Path(args.out_docx)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Load and render template
    print(f"Loading template {args.template}...")
    doc = DocxTemplate(args.template)
    
    # Convert image paths to InlineImage objects
    context = create_image_objects(doc, context)
    
    # Render template
    print("Rendering template...")
    doc.render(context)
    
    # Save output
    doc.save(args.out_docx)
    print(f"Gazette saved to {args.out_docx}")

if __name__ == "__main__":
    main()