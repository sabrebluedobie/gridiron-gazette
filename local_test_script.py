#!/usr/bin/env python3
"""
Local test script to verify everything works before GitHub Actions
Run this locally with your .env file loaded
"""

import os
import json
import sys
from pathlib import Path

def check_requirements():
    """Check if all required packages are installed"""
    print("=== Checking Requirements ===")
    
    required_packages = [
        ('espn_api', 'espn-api'),
        ('openai', 'openai'), 
        ('docxtpl', 'docxtpl'),
        ('PIL', 'pillow')
    ]
    
    missing = []
    for package, pip_name in required_packages:
        try:
            __import__(package)
            print(f"✅ {package} installed")
        except ImportError:
            print(f"❌ {package} missing (install with: pip install {pip_name})")
            missing.append(pip_name)
    
    if missing:
        print(f"\nInstall missing packages: pip install {' '.join(missing)}")
        return False
    return True

def check_files():
    """Check if required files exist"""
    print("\n=== Checking Files ===")
    
    required_files = [
        'leagues.json',
        'build_gazette.py',
        'gazette_data.py', 
        'gazette_helpers.py',
        'mascots_util.py'
    ]
    
    missing = []
    for file in required_files:
        if Path(file).exists():
            print(f"✅ {file}")
        else:
            print(f"❌ {file} missing")
            missing.append(file)
    
    return len(missing) == 0

def check_credentials():
    """Check ESPN and OpenAI credentials"""
    print("\n=== Checking Credentials ===")
    
    # Load from .env if it exists
    env_file = Path('.env')
    if env_file.exists():
        print("Loading .env file...")
        for line in env_file.read_text().split('\n'):
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()
    
    # Check credentials
    espn_s2 = os.getenv('ESPN_S2')
    swid = os.getenv('SWID') 
    openai_key = os.getenv('OPENAI_API_KEY')
    
    print(f"ESPN_S2: {'✅' if espn_s2 else '❌'}")
    print(f"SWID: {'✅' if swid else '❌'}")
    print(f"OPENAI_API_KEY: {'✅' if openai_key else '❌'}")
    
    if not espn_s2 or not swid:
        print("\n❌ Missing ESPN credentials!")
        print("Set ESPN_S2 and SWID in your .env file or environment")
        return False
        
    if not openai_key:
        print("\n⚠️  Missing OpenAI API key (LLM blurbs will be skipped)")
    
    return True

def test_espn_connection():
    """Test ESPN API connection"""
    print("\n=== Testing ESPN Connection ===")
    
    try:
        from espn_api.football import League
        
        # Load config
        leagues = json.loads(Path("leagues.json").read_text())
        config = leagues[0]
        
        league = League(
            league_id=config["league_id"],
            year=config["year"],
            espn_s2=os.getenv("ESPN_S2"),
            swid=os.getenv("SWID")
        )
        
        print(f"✅ Connected to: {league.settings.name}")
        print(f"Teams ({len(league.teams)}):")
        
        team_names = []
        for i, team in enumerate(league.teams, 1):
            print(f"  {i}. {team.team_name}")
            team_names.append(team.team_name)
        
        # Test getting scoreboard
        try:
            scoreboard = league.scoreboard(week=1)
            print(f"\nWeek 1 scoreboard ({len(scoreboard)} games):")
            for i, game in enumerate(scoreboard, 1):
                home = game.home_team.team_name
                away = game.away_team.team_name  
                home_score = getattr(game, 'home_score', 'TBD')
                away_score = getattr(game, 'away_score', 'TBD')
                print(f"  {i}. {home} ({home_score}) vs {away} ({away_score})")
            
            return True, team_names
            
        except Exception as e:
            print(f"❌ Error getting scoreboard: {e}")
            return False, team_names
            
    except Exception as e:
        print(f"❌ ESPN connection failed: {e}")
        return False, []

def create_test_logos(team_names):
    """Create simple test logos"""
    print(f"\n=== Creating Test Logos for {len(team_names)} teams ===")
    
    logos_dir = Path("logos/generated_logos")
    logos_dir.mkdir(parents=True, exist_ok=True)
    
    team_logos = {}
    
    for team in team_names:
        # Create safe filename
        import re
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', team)
        logo_path = logos_dir / f"{safe_name}.png"
        
        # Try to create actual image with PIL
        try:
            from PIL import Image, ImageDraw, ImageFont
            import hashlib
            
            # Simple colored circle with initials
            size = 200
            img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            
            # Color from team name hash
            hash_obj = hashlib.md5(team.encode())
            hex_dig = hash_obj.hexdigest()
            r = max(100, int(hex_dig[0:2], 16))
            g = max(100, int(hex_dig[2:4], 16))
            b = max(100, int(hex_dig[4:6], 16))
            
            # Draw circle
            draw.ellipse([20, 20, size-20, size-20], fill=(r, g, b, 255))
            
            # Add initials
            words = re.findall(r'\b\w', team)
            initials = ''.join(words[:2]).upper()
            
            try:
                font = ImageFont.truetype("arial.ttf", 60)
            except:
                font = ImageFont.load_default()
            
            bbox = draw.textbbox((0, 0), initials, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = (size - text_width) // 2
            y = (size - text_height) // 2
            
            draw.text((x, y), initials, fill=(255, 255, 255, 255), font=font)
            
            img.save(logo_path, 'PNG')
            team_logos[team] = str(logo_path)
            print(f"✅ Created logo for {team}")
            
        except Exception as e:
            # Fallback: create text file
            logo_path.with_suffix('.txt').write_text(f"Logo for {team}")
            team_logos[team] = str(logo_path.with_suffix('.txt'))
            print(f"⚠️  Created text placeholder for {team} (install Pillow for images)")
    
    # Save mapping
    mapping_file = Path("team_logos.json")
    existing = {}
    if mapping_file.exists():
        try:
            existing = json.loads(mapping_file.read_text())
        except:
            pass
    
    existing.update(team_logos)
    mapping_file.write_text(json.dumps(existing, indent=2))
    print(f"✅ Saved {len(team_logos)} logo mappings to team_logos.json")
    
    return len(team_logos)

def test_full_build():
    """Test the full gazette build"""
    print("\n=== Testing Full Build ===")
    
    try:
        # Check if template exists
        template_file = Path("recap_template.docx")
        if not template_file.exists():
            print("❌ recap_template.docx not found!")
            print("Create a Word template with placeholders like {{ MATCHUP1_HOME }}")
            return False
        
        # Run the build command
        import subprocess
        cmd = [
            sys.executable, "build_gazette.py",
            "--template", "recap_template.docx",
            "--out-docx", "test_gazette.docx", 
            "--league-id", "887998",
            "--year", "2025",
            "--week", "1",
            "--llm-blurbs",
            "--blurb-style", "mascot",
            "--blurb-words", "200",
            "--slots", "6"
        ]
        
        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Build successful!")
            print(result.stdout)
            
            if Path("test_gazette.docx").exists():
                print("✅ Output file created: test_gazette.docx")
                return True
            else:
                print("❌ Output file not created")
                return False
        else:
            print("❌ Build failed!")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Build test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("🧪 Testing Gridiron Gazette Setup\n")
    
    # Run tests
    reqs_ok = check_requirements()
    files_ok = check_files()
    creds_ok = check_credentials()
    
    if not all([reqs_ok, files_ok, creds_ok]):
        print("\n❌ Prerequisites not met. Fix the issues above first.")
        return
    
    espn_ok, team_names = test_espn_connection()
    
    if espn_ok and team_names:
        logos_created = create_test_logos(team_names)
        print(f"Created {logos_created} team logos")
    
    if espn_ok:
        build_ok = test_full_build()
    else:
        build_ok = False
    
    # Summary
    print(f"\n=== Summary ===")
    print(f"Requirements: {'✅' if reqs_ok else '❌'}")
    print(f"Files: {'✅' if files_ok else '❌'}")
    print(f"Credentials: {'✅' if creds_ok else '❌'}")
    print(f"ESPN Connection: {'✅' if espn_ok else '❌'}")
    print(f"Full Build: {'✅' if build_ok else '❌'}")
    
    if all([reqs_ok, files_ok, creds_ok, espn_ok, build_ok]):
        print("\n🎉 Everything looks good! Ready for GitHub Actions.")
    else:
        print("\n🔧 Fix the issues above before running GitHub Actions.")

if __name__ == "__main__":
    main()