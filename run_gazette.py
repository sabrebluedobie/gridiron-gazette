#!/usr/bin/env python3
"""
run_gazette.py - Quick shortcut script for local development
Save this in your project root and run: python run_gazette.py
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

# ==================== CONFIGURATION ====================
# Update these with your actual values

LEAGUE_ID = "YOUR_LEAGUE_ID_HERE"  # Your ESPN League ID
YEAR = 2024
FANTASY_SEASON_START = "2024-09-05"  # Adjust to your league's start date

# Optional: Set these as environment variables instead
# ESPN_S2 = "your_espn_s2_cookie"
# SWID = "your_swid_cookie" 
# OPENAI_API_KEY = "your_openai_api_key"

# ==================== AUTO WEEK CALCULATION ====================
def get_current_week():
    """Calculate current week based on season start"""
    try:
        start_date = datetime.strptime(FANTASY_SEASON_START, "%Y-%m-%d")
        current_date = datetime.now()
        week = min(18, max(1, ((current_date - start_date).days // 7) + 1))
        return week
    except:
        return 1  # Fallback to week 1

# ==================== MAIN FUNCTION ====================
def main():
    print("🏈 GRIDIRON GAZETTE - QUICK BUILD")
    print("=" * 50)
    
    # Validate configuration
    if LEAGUE_ID == "YOUR_LEAGUE_ID_HERE":
        print("❌ Please update LEAGUE_ID in run_gazette.py")
        print("   Edit the LEAGUE_ID variable at the top of this file")
        sys.exit(1)
    
    # Get week input
    current_week = get_current_week()
    print(f"📅 Current calculated week: {current_week}")
    
    week_input = input(f"Enter week to build (or press Enter for {current_week}): ").strip()
    week = int(week_input) if week_input.isdigit() else current_week
    
    # Get build options
    print("\n🔧 Build Options:")
    print("1. Normal build (no LLM blurbs)")
    print("2. Enhanced build (with LLM blurbs)")
    print("3. Debug mode")
    print("4. Test API connection")
    
    choice = input("Select option (1-4, or Enter for 1): ").strip()
    
    # Build command based on choice
    if choice == "2":
        # Enhanced build with LLM
        print(f"\n🤖 Building Week {week} with LLM blurbs...")
        cmd_args = [
            sys.executable, "gazette_main.py" if Path("gazette_main.py").exists() else "build_gazette.py",
            str(LEAGUE_ID), str(YEAR), str(week),
            "--llm-blurbs", "--style", "sabre", "--verbose"
        ]
    elif choice == "3":
        # Debug mode
        print(f"\n🔍 Running debug analysis for Week {week}...")
        cmd_args = [
            sys.executable, "gazette_main.py" if Path("gazette_main.py").exists() else "build_gazette.py", 
            str(LEAGUE_ID), str(YEAR), str(week),
            "--debug"
        ]
    elif choice == "4":
        # Test API
        print(f"\n🧪 Testing API connection for Week {week}...")
        cmd_args = [
            sys.executable, "gazette_main.py" if Path("gazette_main.py").exists() else "build_gazette.py",
            str(LEAGUE_ID), str(YEAR), str(week),
            "--test-api"
        ]
    else:
        # Normal build
        print(f"\n📄 Building Week {week} (normal mode)...")
        cmd_args = [
            sys.executable, "gazette_main.py" if Path("gazette_main.py").exists() else "build_gazette.py",
            str(LEAGUE_ID), str(YEAR), str(week),
            "--verbose"
        ]
    
    # Check for required files
    required_files = ["recap_template.docx"]
    missing_files = [f for f in required_files if not Path(f).exists()]
    
    if missing_files:
        print(f"\n⚠️  WARNING: Missing required files: {', '.join(missing_files)}")
        if not input("Continue anyway? (y/n): ").lower().startswith('y'):
            sys.exit(1)
    
    # Setup environment
    print("\n🔧 Setting up environment...")
    
    # Create required directories
    for dir_name in ["recaps", "logs", "logos/team_logos", "logos/league_logos", "logos/sponsor_logos"]:
        Path(dir_name).mkdir(parents=True, exist_ok=True)
    
    # Create basic mapping files if needed
    import json
    mapping_files = {
        "team_logos.json": {},
        "league_logos.json": {}, 
        "sponsor_logos.json": {}
    }
    
    for filename, default_content in mapping_files.items():
        if not Path(filename).exists():
            with open(filename, 'w') as f:
                json.dump(default_content, f, indent=2)
            print(f"   ✅ Created {filename}")
    
    # Run the command
    print(f"\n🚀 Running: {' '.join(cmd_args)}")
    print("=" * 50)
    
    try:
        import subprocess
        result = subprocess.run(cmd_args, check=False)
        
        if result.returncode == 0:
            print("\n" + "=" * 50)
            print("✅ Build completed successfully!")
            
            # Show output files
            output_dir = Path("recaps")
            if output_dir.exists():
                docx_files = list(output_dir.glob("*.docx"))
                if docx_files:
                    print(f"📄 Generated files:")
                    for file in docx_files:
                        size_kb = file.stat().st_size / 1024
                        print(f"   📄 {file} ({size_kb:.1f}KB)")
                else:
                    print("   ⚠️  No .docx files found in recaps/")
            
            # Show logs
            log_file = Path("gazette.log")
            if log_file.exists():
                print(f"\n📋 Check gazette.log for detailed information")
        else:
            print(f"\n❌ Build failed with exit code {result.returncode}")
            print("📋 Check gazette.log for error details")
            
    except FileNotFoundError:
        print(f"\n❌ Script not found. Available scripts:")
        for script in ["gazette_main.py", "build_gazette.py", "weekly_recap.py"]:
            if Path(script).exists():
                print(f"   ✅ {script}")
            else:
                print(f"   ❌ {script}")
        
    except KeyboardInterrupt:
        print(f"\n⏹️  Build cancelled by user")
        
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")

if __name__ == "__main__":
    main()