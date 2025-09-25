"""
Gridiron Gazette Story Generator - Sabre Voice
Handles OpenAI integration for generating Sabre's witty commentary
Includes markdown to DOCX conversion
"""

import os
import re
import logging
from typing import Dict, List, Any, Optional

log = logging.getLogger("storymaker")

# ================= Configuration =================

SABRE_SIGNATURE = "— Sabre, Gridiron Gazette"

# OpenAI SDK detection and import
_OPENAI_AVAILABLE = False
_OPENAI_CLIENT = None

try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
    log.info("OpenAI SDK available")
except ImportError:
    log.warning("OpenAI SDK not available - will use fallback blurbs")

# ================= Markdown Conversion =================

def clean_markdown_for_docx(text: str) -> str:
    """
    Convert markdown formatting to plain text for DOCX templates
    Removes markdown syntax while preserving the actual content
    """
    if not text:
        return text
    
    # Remove bold markdown (**text** or __text__ -> text)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    
    # Remove italic markdown (*text* or _text_ -> text)
    # Be careful not to remove single asterisks that aren't markdown
    text = re.sub(r'(?<!\*)\*(?!\*)([^\*]+)\*(?!\*)', r'\1', text)
    text = re.sub(r'(?<!_)_(?!_)([^_]+)_(?!_)', r'\1', text)
    
    # Remove code backticks (`text` -> text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    
    # Remove headers (### text -> text)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    
    # Remove strikethrough (~~text~~ -> text)
    text = re.sub(r'~~(.*?)~~', r'\1', text)
    
    # Remove blockquotes (> text -> text)
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    
    # Clean up any remaining artifacts
    text = text.strip()
    
    return text

# ================= Sabre Prompt System =================

def get_sabre_system_prompt() -> str:
    """Get Sabre's system prompt for consistent voice"""
    return """You are Sabre, the witty Doberman mascot and beat reporter for the Gridiron Gazette.

PERSONALITY:
- Sharp-tongued but fair
- Clever wordplay and puns
- Never mean-spirited, always entertaining
- Professional sports journalist with personality
- Respects the game but calls out poor performances

WRITING STYLE:
- First-person perspective as Sabre the Doberman
- Conversational but informative
- Focus on specific stats and performances
- Highlight decisive moments and standout players
- Call out both heroes and disappointments
- Use dog-related puns sparingly but effectively

RULES:
- NO profanity or inappropriate content
- Use actual data provided, don't invent stats
- Keep it concise but memorable
- End with your signature: "— Sabre, Gridiron Gazette"
"""

def get_sabre_matchup_prompt(matchup_data: Dict[str, Any], week: int) -> str:
    """Generate the specific prompt for a matchup"""
    home = matchup_data.get('home_team', 'Home Team')
    away = matchup_data.get('away_team', 'Away Team')
    home_score = matchup_data.get('home_score', 0)
    away_score = matchup_data.get('away_score', 0)
    
    # Extract top performers
    home_top = matchup_data.get('home_top_scorer', 'Unknown')
    home_pts = matchup_data.get('home_top_points', 0)
    away_top = matchup_data.get('away_top_scorer', 'Unknown')
    away_pts = matchup_data.get('away_top_points', 0)
    
    # Extract other notable performances
    home_bust = matchup_data.get('home_bust', '')
    away_bust = matchup_data.get('away_bust', '')
    
    prompt = f"""Write a 5-line news article about this Week {week} fantasy matchup:

FINAL SCORE: {home} {home_score} - {away} {away_score}

TOP PERFORMERS:
- {home} best: {home_top} ({home_pts} points)
- {away} best: {away_top} ({away_pts} points)

DISAPPOINTMENTS:
- {home}: {home_bust if home_bust else 'None notable'}
- {away}: {away_bust if away_bust else 'None notable'}

Write exactly 5 lines (each 10-20 words) covering:
1. The final outcome with a clever observation
2. Top performer highlights
3. Biggest disappointment or surprise
4. Key matchup factor that decided the game
5. A witty closing line about what this means going forward

Remember: You're Sabre the Doberman, be witty but informative!
End with: — Sabre, Gridiron Gazette"""
    
    return prompt

# ================= OpenAI Integration =================

def initialize_openai_client() -> Optional[Any]:
    """Initialize OpenAI client if available"""
    global _OPENAI_CLIENT
    
    if not _OPENAI_AVAILABLE:
        return None
    
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        log.warning("No OpenAI API key found")
        return None
    
    # Remove any smart quotes that might have been copied
    api_key = api_key.replace('"', '').replace('"', '').replace("'", '').replace("'", '')
    
    try:
        _OPENAI_CLIENT = OpenAI(api_key=api_key)
        log.info("OpenAI client initialized successfully")
        return _OPENAI_CLIENT
    except Exception as e:
        log.error(f"Failed to initialize OpenAI client: {e}")
        return None

def generate_sabre_blurb_openai(matchup_data: Dict[str, Any], week: int) -> str:
    """Generate a single Sabre blurb using OpenAI"""
    client = _OPENAI_CLIENT or initialize_openai_client()
    
    if not client:
        return generate_fallback_sabre_blurb(matchup_data, week)
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.8,
            max_tokens=200,
            messages=[
                {"role": "system", "content": get_sabre_system_prompt()},
                {"role": "user", "content": get_sabre_matchup_prompt(matchup_data, week)}
            ]
        )
        
        content = response.choices[0].message.content.strip()
        # Clean markdown before returning
        content = clean_markdown_for_docx(content)
        
        # Ensure signature is present
        if SABRE_SIGNATURE not in content:
            content += f"\n{SABRE_SIGNATURE}"
        
        return content
        
    except Exception as e:
        log.error(f"OpenAI API error: {e}")
        return generate_fallback_sabre_blurb(matchup_data, week)

# ================= Fallback Generation =================

def generate_fallback_sabre_blurb(matchup_data: Dict[str, Any], week: int) -> str:
    """Generate fallback Sabre-style commentary when OpenAI is unavailable"""
    home = matchup_data.get('home_team', 'Home Team')
    away = matchup_data.get('away_team', 'Away Team')
    home_score = float(matchup_data.get('home_score', 0))
    away_score = float(matchup_data.get('away_score', 0))
    
    winner = home if home_score > away_score else away
    loser = away if home_score > away_score else home
    margin = abs(home_score - away_score)
    
    # Determine game narrative
    if margin < 3:
        outcome = "squeaked by"
        narrative = "a nail-biter that came down to the wire"
    elif margin < 10:
        outcome = "edged out"
        narrative = "a competitive matchup"
    elif margin < 20:
        outcome = "defeated"
        narrative = "a solid victory"
    elif margin < 40:
        outcome = "dominated"
        narrative = "an impressive performance"
    else:
        outcome = "absolutely demolished"
        narrative = "a complete blowout"
    
    # Get top performers
    home_top = matchup_data.get('home_top_scorer', 'their top player')
    home_pts = matchup_data.get('home_top_points', 'big')
    away_top = matchup_data.get('away_top_scorer', 'their best performer')
    away_pts = matchup_data.get('away_top_points', 'solid')
    
    # Build the blurb
    lines = [
        f"{winner} {outcome} {loser} {home_score:.2f}-{away_score:.2f} in {narrative}.",
        f"{home}'s {home_top} led the charge with {home_pts} points.",
        f"{away} countered with {away_top} putting up {away_pts} points.",
        f"The {margin:.2f}-point margin tells the whole story here.",
        f"This dog's nose knows {winner} had this one all along.",
        f"{SABRE_SIGNATURE}"
    ]
    
    return "\n".join(lines)

# ================= Main Entry Points =================

def generate_sabre_blurbs(context: Dict[str, Any]) -> Dict[str, str]:
    """
    Generate Sabre blurbs for all matchups in the context
    Returns dictionary with keys '1', '2', '3' etc for each matchup
    """
    week = context.get('WEEK', 1)
    blurbs = {}
    
    # Initialize OpenAI if available
    initialize_openai_client()
    
    # Process each matchup (typically 1-7)
    for i in range(1, 8):
        matchup_key = f"MATCHUP{i}"
        
        # Check if matchup exists
        home_team = context.get(f"{matchup_key}_HOME")
        away_team = context.get(f"{matchup_key}_AWAY")
        
        if not home_team or not away_team:
            continue
        
        # Build matchup data
        matchup_data = {
            'home_team': home_team,
            'away_team': away_team,
            'home_score': context.get(f"{matchup_key}_HS", 0),
            'away_score': context.get(f"{matchup_key}_AS", 0),
            'home_top_scorer': context.get(f"{matchup_key}_HOME_TOP_SCORER", "Unknown"),
            'home_top_points': context.get(f"{matchup_key}_HOME_TOP_POINTS", 0),
            'away_top_scorer': context.get(f"{matchup_key}_AWAY_TOP_SCORER", "Unknown"),
            'away_top_points': context.get(f"{matchup_key}_AWAY_TOP_POINTS", 0),
            'home_bust': context.get(f"{matchup_key}_HOME_BUST", ""),
            'away_bust': context.get(f"{matchup_key}_AWAY_BUST", "")
        }
        
        # Generate blurb (will use OpenAI if available, fallback otherwise)
        if _OPENAI_CLIENT:
            blurb = generate_sabre_blurb_openai(matchup_data, week)
        else:
            blurb = generate_fallback_sabre_blurb(matchup_data, week)
        
        blurbs[str(i)] = blurb
        log.info(f"Generated Sabre blurb for matchup {i}")
    
    return blurbs

def generate_spotlight_content(context: Dict[str, Any]) -> Dict[str, str]:
    """
    Generate Stats Spotlight content for the template
    This creates the TOP_HOME, TOP_AWAY, BUST, DEF, and KEYPLAY content
    """
    spotlights = {}
    week = context.get('WEEK', 1)
    
    # Process each matchup
    for i in range(1, 8):
        matchup_key = f"MATCHUP{i}"
        
        # Check if matchup exists
        if not context.get(f"{matchup_key}_HOME"):
            continue
        
        # Build matchup data for Sabre commentary
        matchup_data = {
            'home_team': context.get(f"{matchup_key}_HOME"),
            'away_team': context.get(f"{matchup_key}_AWAY"),
            'home_score': context.get(f"{matchup_key}_HS", 0),
            'away_score': context.get(f"{matchup_key}_AS", 0),
            'home_top_scorer': context.get(f"{matchup_key}_HOME_TOP_SCORER", "Unknown"),
            'home_top_points': context.get(f"{matchup_key}_HOME_TOP_POINTS", 0),
            'away_top_scorer': context.get(f"{matchup_key}_AWAY_TOP_SCORER", "Unknown"),
            'away_top_points': context.get(f"{matchup_key}_AWAY_TOP_POINTS", 0)
        }
        
        # Generate full Sabre commentary
        if _OPENAI_CLIENT:
            full_blurb = generate_sabre_blurb_openai(matchup_data, week)
        else:
            full_blurb = generate_fallback_sabre_blurb(matchup_data, week)
        
        # Split the blurb into sections for the template
        lines = full_blurb.split('\n')
        
        # Assign lines to specific spotlight sections
        if len(lines) >= 5:
            spotlights[f"{matchup_key}_TOP_HOME"] = lines[1] if len(lines) > 1 else f"{matchup_data['home_team']}'s {matchup_data['home_top_scorer']} delivered."
            spotlights[f"{matchup_key}_TOP_AWAY"] = lines[2] if len(lines) > 2 else f"{matchup_data['away_team']}'s {matchup_data['away_top_scorer']} showed up."
            spotlights[f"{matchup_key}_BUST"] = lines[3] if len(lines) > 3 else "Both teams had their struggles this week."
            spotlights[f"{matchup_key}_DEF"] = lines[4] if len(lines) > 4 else "Defense wasn't the story in this matchup."
            spotlights[f"{matchup_key}_KEYPLAY"] = lines[0] if len(lines) > 0 else "Every point mattered in this one."
        else:
            # Fallback if blurb is shorter
            spotlights[f"{matchup_key}_TOP_HOME"] = f"{matchup_data['home_team']}'s top performer: {matchup_data['home_top_scorer']}"
            spotlights[f"{matchup_key}_TOP_AWAY"] = f"{matchup_data['away_team']}'s best: {matchup_data['away_top_scorer']}"
            spotlights[f"{matchup_key}_BUST"] = "Both teams battled hard this week."
            spotlights[f"{matchup_key}_DEF"] = "Defense played its part."
            spotlights[f"{matchup_key}_KEYPLAY"] = full_blurb.split('\n')[0] if full_blurb else "Close matchup decided by key plays."
    
    return spotlights

# ================= Testing Interface =================

def test_openai_connection() -> bool:
    """Test if OpenAI API is properly configured and working"""
    client = initialize_openai_client()
    if not client:
        return False
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=10,
            messages=[
                {"role": "user", "content": "Say 'API working'"}
            ]
        )
        result = response.choices[0].message.content
        return "working" in result.lower()
    except Exception as e:
        log.error(f"OpenAI test failed: {e}")
        return False

def test_markdown_conversion():
    """Test the markdown conversion function"""
    test_cases = [
        ("**Bold Text**", "Bold Text"),
        ("*Italic Text*", "Italic Text"),
        ("__Also Bold__", "Also Bold"),
        ("_Also Italic_", "Also Italic"),
        ("`Code Text`", "Code Text"),
        ("### Header Text", "Header Text"),
        ("~~Strikethrough~~", "Strikethrough"),
        ("> Quoted text", "Quoted text"),
        ("**Top Play**: The big moment", "Top Play: The big moment"),
        ("Normal text with **bold** and *italic* mixed", "Normal text with bold and italic mixed")
    ]
    
    print("Testing markdown conversion:")
    for input_text, expected in test_cases:
        result = clean_markdown_for_docx(input_text)
        status = "✅" if result == expected else "❌"
        print(f"{status} '{input_text}' -> '{result}' (expected: '{expected}')")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "test":
            print("Testing OpenAI connection...")
            if test_openai_connection():
                print("✅ OpenAI API connected successfully")
            else:
                print("❌ OpenAI API connection failed")
            
            print("\n" + "="*50 + "\n")
            test_markdown_conversion()
        
        elif sys.argv[1] == "test-blurb":
            # Test blurb generation with sample data
            test_data = {
                'home_team': 'Thunder Hawks',
                'away_team': 'Lightning Bolts', 
                'home_score': 125.5,
                'away_score': 98.3,
                'home_top_scorer': 'Josh Allen',
                'home_top_points': 32.5,
                'away_top_scorer': 'Justin Jefferson',
                'away_top_points': 28.2
            }
            
            print("Generating test Sabre blurb...")
            blurb = generate_sabre_blurb_openai(test_data, 3)
            print("\n" + "="*50)
            print(blurb)
            print("="*50)
    else:
        print("Gridiron Gazette Story Generator")
        print("Usage:")
        print("  python storymaker.py test           - Test OpenAI connection")
        print("  python storymaker.py test-blurb     - Generate sample blurb")