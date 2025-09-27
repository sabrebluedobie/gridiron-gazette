#!/usr/bin/env python3
"""
Setup Helper for Gridiron Gazette HTML/PDF Generation
Helps set up the environment and verify everything is working
"""
import os
import sys
import json
import subprocess
from pathlib import Path


def check_python_version():
    """Ensure Python 3.8+ is being used"""
    if sys.version_info < (3, 8):
        print(f"❌ Python 3.8+ required (you have {sys.version})")
        return False
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} detected")
    return True


def check_python_packages():
    """Check and install required Python packages"""
    required = {
        'jinja2': 'Jinja2',
        'pdfkit': 'pdfkit',
        'espn_api': 'espn-api',
        'docxtpl': 'docxtpl',  # Still needed for existing DOCX support
        'dotenv': 'python-dotenv',
        'PIL': 'pillow',
    }
    
    missing = []
    
    for import_name, package_name in required.items():
        try:
            if import_name == 'PIL':
                from PIL import Image
            elif import_name == 'dotenv':
                from dotenv import load_dotenv
            else:
                __import__(import_name)
            print(f"✅ {package_name} is installed")
        except ImportError:
            print(f"❌ {package_name} not installed")
            missing.append(package_name)
    
    if missing:
        print(f"\n📦 Installing missing packages: {', '.join(missing)}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
            print("✅ Packages installed successfully")
            return True
        except subprocess.CalledProcessError:
            print("❌ Failed to install packages")
            print(f"Run manually: pip install {' '.join(missing)}")
            return False
    
    return True


def check_wkhtmltopdf():
    """Check if wkhtmltopdf is installed"""
    try:
        import pdfkit
        config = pdfkit.configuration()
        print(f"✅ wkhtmltopdf is installed")
        return True
    except Exception as e:
        print(f"❌ wkhtmltopdf not found")
        print("\nInstall wkhtmltopdf:")
        
        if sys.platform == "darwin":  # macOS
            print("  Mac: brew install wkhtmltopdf")
            print("       or download from https://wkhtmltopdf.org/downloads.html")
        elif sys.platform == "win32":  # Windows
            print("  Windows: Download installer from https://wkhtmltopdf.org/downloads.html")
            print("          Add to PATH after installation")
        else:  # Linux
            print("  Ubuntu/Debian: sudo apt-get install wkhtmltopdf")
            print("  Fedora: sudo dnf install wkhtmltopdf")
            print("  Or download from https://wkhtmltopdf.org/downloads.html")
        
        return False


def setup_directories():
    """Create necessary directories"""
    dirs = [
        Path("templates"),
        Path("recaps"),
        Path("logos/team_logos"),
        Path("logos/league_logos"),
        Path("logos/sponsor_logos"),
    ]
    
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        print(f"✅ Directory ready: {d}")
    
    return True


def check_template():
    """Check if HTML template exists"""
    template_paths = [
        Path("templates/recap_template.html"),
        Path("recap_template.html"),
    ]
    
    for path in template_paths:
        if path.exists():
            print(f"✅ Template found: {path}")
            return True
    
    print("❌ HTML template not found")
    print("   Save the template as: templates/recap_template.html")
    return False


def check_env_file():
    """Check for .env file with ESPN credentials"""
    env_file = Path(".env")
    
    if env_file.exists():
        print("✅ .env file found")
        
        # Check for required variables
        from dotenv import load_dotenv
        load_dotenv()
        
        missing = []
        if not os.getenv("ESPN_S2"):
            missing.append("ESPN_S2")
        if not os.getenv("SWID") and not os.getenv("ESPN_SWID"):
            missing.append("SWID or ESPN_SWID")
        if not os.getenv("LEAGUE_ID"):
            missing.append("LEAGUE_ID")
        
        if missing:
            print(f"⚠️  Missing in .env: {', '.join(missing)}")
            print("\nAdd these to your .env file:")
            print("ESPN_S2=your_espn_s2_cookie")
            print("SWID={your_swid_cookie_with_braces}")
            print("LEAGUE_ID=your_league_id")
            print("YEAR=2025")
            return False
        else:
            print("✅ All ESPN credentials present")
            return True
    else:
        print("❌ .env file not found")
        print("\nCreate a .env file with:")
        print("ESPN_S2=your_espn_s2_cookie")
        print("SWID={your_swid_cookie_with_braces}")
        print("LEAGUE_ID=your_league_id")
        print("YEAR=2025")
        print("OPENAI_API_KEY=your_key  # Optional for Sabre LLM")
        return False


def check_team_logos():
    """Check team_logos.json file"""
    logo_file = Path("team_logos.json")
    
    if not logo_file.exists():
        print("⚠️  team_logos.json not found")
        print("   Creating template file...")
        
        template = {
            "LEAGUE_LOGO": "logos/league_logos/your_league.png",
            "SPONSOR_LOGO": "logos/sponsor_logos/gazette_logo.png",
            "Team Name 1": "logos/team_logos/team1.png",
            "Team Name 2": "logos/team_logos/team2.png",
            "// Note": "Add all your team names and logo paths here"
        }
        
        with open(logo_file, 'w') as f:
            json.dump(template, f, indent=2)
        
        print("✅ Created template team_logos.json")
        print("   Edit it with your team names and logo paths")
        return False
    
    print("✅ team_logos.json found")
    
    # Check if logo files exist
    with open(logo_file, 'r') as f:
        logos = json.load(f)
    
    missing = 0
    for team, path in logos.items():
        if team.startswith("//"):  # Skip comments
            continue
        if not Path(path).exists():
            if missing == 0:
                print("⚠️  Missing logo files:")
            missing += 1
            if missing <= 5:  # Show first 5
                print(f"   - {path} (for {team})")
    
    if missing > 5:
        print(f"   ... and {missing - 5} more")
    
    return missing == 0


def run_test():
    """Run a quick test to verify everything works"""
    print("\n" + "="*60)
    print("RUNNING TEST")
    print("="*60)
    
    try:
        # Test imports
        print("Testing imports...")
        import weekly_recap
        import gazette_data
        from storymaker import StoryMaker
        print("✅ All modules imported successfully")
        
        # Test template rendering
        print("\nTesting template rendering...")
        from jinja2 import Environment, FileSystemLoader
        
        test_context = {
            "LEAGUE_LOGO": "Test League",
            "WEEK_NUMBER": "1",
            "WEEKLY_INTRO": "Test week intro",
            "MATCHUP1_HOME": "Test Team A",
            "MATCHUP1_AWAY": "Test Team B",
            "MATCHUP1_HS": "100.5",
            "MATCHUP1_AS": "95.2",
            "MATCHUP1_BLURB": "Test matchup narrative",
            "AWARD_CUPCAKE_TEAM": "Test Team C",
            "AWARD_CUPCAKE_NOTE": "50.1",
        }
        
        template_path = Path("templates/recap_template.html")
        if template_path.exists():
            env = Environment(loader=FileSystemLoader("templates"))
            template = env.get_template("recap_template.html")
            html = template.render(**test_context)
            print(f"✅ Template rendered ({len(html)} characters)")
        else:
            print("⚠️  Skipping template test (template not found)")
        
        print("\n✅ All tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def main():
    print("="*60)
    print("GRIDIRON GAZETTE SETUP HELPER")
    print("="*60)
    print()
    
    checks = [
        ("Python Version", check_python_version),
        ("Python Packages", check_python_packages),
        ("wkhtmltopdf", check_wkhtmltopdf),
        ("Directories", setup_directories),
        ("HTML Template", check_template),
        ("Environment File", check_env_file),
        ("Team Logos", check_team_logos),
    ]
    
    results = {}
    for name, check_func in checks:
        print(f"\n📋 Checking {name}...")
        print("-" * 40)
        results[name] = check_func()
        print()
    
    # Summary
    print("="*60)
    print("SETUP SUMMARY")
    print("="*60)
    
    all_good = True
    for name, result in results.items():
        status = "✅" if result else "❌"
        print(f"{status} {name}")
        if not result:
            all_good = False
    
    if all_good:
        print("\n🎉 Everything is set up correctly!")
        
        # Run test
        if input("\nRun a quick test? (y/n): ").lower() == 'y':
            run_test()
        
        print("\n📚 Next steps:")
        print("1. Make sure your ESPN credentials are in .env")
        print("2. Update team_logos.json with your team names")
        print("3. Run: python build_gazette.py --verify")
        print("4. Generate gazette: python build_gazette.py")
        
    else:
        print("\n⚠️  Some setup steps need attention")
        print("Fix the issues above and run this script again")
    
    print("="*60)


if __name__ == "__main__":
    main()