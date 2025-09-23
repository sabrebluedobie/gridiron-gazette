#!/usr/bin/env python3
"""
setup_gazette.py - Setup and validation script for Gridiron Gazette

This script helps you:
1. Install required dependencies
2. Set up directory structure
3. Create configuration files
4. Validate your setup
5. Test ESPN and OpenAI connections
"""

import os
import sys
import subprocess
import json
from pathlib import Path

def print_banner():
    """Print setup banner"""
    print("🏈 GRIDIRON GAZETTE SETUP")
    print("=" * 50)
    print("Setting up your fantasy football newsletter generator")
    print()

def check_python_version():
    """Check if Python version is compatible"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 3.8+ required. You have:", sys.version)
        return False
    print(f"✅ Python {version.major}.{version.minor}.{version.micro}")
    return True

def install_dependencies():
    """Install required Python packages"""
    print("\n📦 Installing dependencies...")
    
    requirements = [
        "docxtpl==0.16.7",
        "python-docx==1.1.2", 
        "espn-api==0.45.1",
        "openai>=1.0.0",
        "python-dotenv==1.0.1",
        "requests==2.32.3"
    ]
    
    try:
        for package in requirements:
            print(f"   Installing {package}...")
            subprocess.run([
                sys.executable, "-m", "pip", "install", package
            ], check=True, capture_output=True)
        
        print("✅ All dependencies installed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False

def create_directories():
    """Create required directory structure"""
    print("\n📁 Creating directory structure...")
    
    directories = [
        "recaps",
        "logs",
        "logos/team_logos",
        "logos/league_logos", 
        "logos/sponsor_logos"
    ]
    
    for dir_path in directories:
        path = Path(dir_path)
        path.mkdir(parents=True, exist_ok=True)
        print(f"   ✅ {dir_path}")
    
    print("✅ Directory structure created")
    return True

def create_config_files():
    """Create default configuration files"""
    print("\n⚙️ Creating configuration files...")
    
    # Create team logos mapping
    if not Path("team_logos.json").exists():
        default_logos = {
            "LEAGUE_LOGO": "logos/team_logos/league.png",
            "SPONSOR_LOGO": "logos/team_logos/gazette_logo.png"
        }
        
        with open("team_logos.json", "w") as f:
            json.dump(default_logos, f, indent=2)
        print("   ✅ team_logos.json")
    else:
        print("   ↻ team_logos.json (already exists)")
    
    # Create .env file if it doesn't exist
    if not Path(".env").exists():
        env_content = """# Gridiron Gazette Configuration
# Copy your actual values here

# ESPN League Configuration
LEAGUE_ID=887998
YEAR=2025
LEAGUE_DISPLAY_NAME="Your League Name"

# ESPN Authentication (get from browser cookies)
ESPN_S2=your_espn_s2_cookie_here
SWID=your_swid_cookie_here

# OpenAI API Key (optional, for AI commentary)
OPENAI_API_KEY=your_openai_api_key_here

# File Paths
TEMPLATE=recap_template.docx
OUTDOCX=recaps/Week{week}_Gazette.docx
TEAM_LOGOS_FILE=team_logos.json

# Settings
VERBOSE=true
"""
        with open(".env", "w") as f:
            f.write(env_content)
        print("   ✅ .env")
    else:
        print("   ↻ .env (already exists)")
    
    # Create sample gazette.yml
    if not Path("gazette.yml").exists():
        yml_content = """# Gazette Configuration
league_id: 887998
year: 2025
week: 0
auto_week: true

league_display_name: "Your League Name"
template: recap_template.docx
outdocx: "recaps/Week{week}_Gazette.docx"

llm_blurbs: true
blurb_style: sabre
blurb_words: 200

verbose: true
"""
        with open("gazette.yml", "w") as f:
            f.write(yml_content)
        print("   ✅ gazette.yml")
    else:
        print("   ↻ gazette.yml (already exists)")
    
    return True

def check_template_file():
    """Check if template file exists"""
    print("\n📄 Checking template file...")
    
    template_file = Path("recap_template.docx")
    if template_file.exists():
        print("   ✅ recap_template.docx found")
        return True
    else:
        print("   ❌ recap_template.docx not found")
        print("   You need to provide your own Word template file")
        print("   Place it in the root directory as 'recap_template.docx'")
        return False

def validate_env_file():
    """Validate .env file configuration"""
    print("\n🔧 Validating configuration...")
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print("   ⚠️ python-dotenv not installed")
        return False
    
    issues = []
    warnings = []
    
    # Check required values
    league_id = os.getenv('LEAGUE_ID')
    if not league_id or league_id == 'your_league_id_here':
        issues.append("LEAGUE_ID not configured")
    
    espn_s2 = os.getenv('ESPN_S2')
    if not espn_s2 or 'your_' in espn_s2:
        issues.append("ESPN_S2 cookie not configured")
    
    swid = os.getenv('SWID')
    if not swid or 'your_' in swid:
        issues.append("SWID cookie not configured")
    
    # Check optional values
    openai_key = os.getenv('OPENAI_API_KEY')
    if not openai_key or 'your_' in openai_key:
        warnings.append("OPENAI_API_KEY not configured (AI commentary disabled)")
    
    # Report results
    if issues:
        print("   ❌ Configuration issues:")
        for issue in issues:
            print(f"      - {issue}")
    
    if warnings:
        print("   ⚠️ Configuration warnings:")
        for warning in warnings:
            print(f"      - {warning}")
    
    if not issues and not warnings:
        print("   ✅ Configuration looks good")
        return True
    elif not issues:
        print("   ⚠️ Configuration has warnings but will work")
        return True
    else:
        return False

def test_connections():
    """Test ESPN and OpenAI connections"""
    print("\n🧪 Testing connections...")
    
    # Load environment
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print("   ❌ Cannot load environment variables")
        return False
    
    # Test ESPN connection
    try:
        from espn_api.football import League
        
        league_id = os.getenv('LEAGUE_ID')
        year = int(os.getenv('YEAR', '2025'))
        espn_s2 = os.getenv('ESPN_S2')
        swid = os.getenv('SWID')
        
        if league_id and espn_s2 and swid:
            league = League(
                league_id=int(league_id),
                year=year,
                espn_s2=espn_s2,
                swid=swid
            )
            teams = league.teams
            print(f"   ✅ ESPN API: Connected to '{league.settings.name}' ({len(teams)} teams)")
        else:
            print("   ⚠️ ESPN API: Missing credentials, cannot test")
            
    except Exception as e:
        print(f"   ❌ ESPN API: {e}")
    
    # Test OpenAI connection
    try:
        openai_key = os.getenv('OPENAI_API_KEY')
        if openai_key and 'your_' not in openai_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=openai_key)
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": "Say 'test successful'"}],
                    max_tokens=10
                )
                print("   ✅ OpenAI API: Connected and working")
            except Exception as e:
                print(f"   ❌ OpenAI API: {e}")
        else:
            print("   ⚠️ OpenAI API: No API key configured")
            
    except ImportError:
        print("   ❌ OpenAI SDK not installed")
    
    return True

def show_next_steps():
    """Show what to do next"""
    print("\n🎯 NEXT STEPS")
    print("=" * 50)
    print("1. Configure your .env file with:")
    print("   - Your ESPN League ID") 
    print("   - ESPN cookies (ESPN_S2 and SWID)")
    print("   - OpenAI API key (optional)")
    print()
    print("2. Add your Word template file:")
    print("   - Save as 'recap_template.docx' in this directory")
    print()
    print("3. Test the setup:")
    print("   python gazette_main.py <league_id> 2025 1 --test-api")
    print()
    print("4. Generate your first gazette:")
    print("   python gazette_main.py <league_id> 2025 1 --llm-blurbs")
    print()
    print("📚 For help getting ESPN cookies:")
    print("   1. Log into ESPN Fantasy in your browser")
    print("   2. Open Developer Tools (F12)")
    print("   3. Go to Application > Cookies > espn.com")
    print("   4. Copy ESPN_S2 and SWID values")

def main():
    """Main setup function"""
    print_banner()
    
    success = True
    
    # Check Python version
    if not check_python_version():
        success = False
    
    # Install dependencies
    if success:
        if not install_dependencies():
            success = False
    
    # Create directories
    if success:
        create_directories()
    
    # Create config files
    if success:
        create_config_files()
    
    # Check template
    template_exists = check_template_file()
    
    # Validate configuration
    config_valid = validate_env_file()
    
    # Test connections if config is valid
    if config_valid:
        test_connections()
    
    # Show results
    print("\n" + "=" * 50)
    if success and template_exists and config_valid:
        print("✅ SETUP COMPLETE!")
        print("Your Gridiron Gazette is ready to use.")
    elif success:
        print("⚠️ SETUP MOSTLY COMPLETE")
        print("Review the issues above and complete configuration.")
    else:
        print("❌ SETUP FAILED")
        print("Please fix the errors above and run setup again.")
    
    show_next_steps()
    
    return 0 if (success and template_exists and config_valid) else 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️ Setup cancelled by user")
        sys.exit(130)