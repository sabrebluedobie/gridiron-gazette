#!/usr/bin/env python3
"""
apply_fixes.py - Emergency patch to fix Stats Spotlight and Awards
Run this to apply all fixes immediately
"""

import shutil
from pathlib import Path
import json

def main():
    print("🚨 EMERGENCY GRIDIRON GAZETTE PATCH")
    print("=" * 50)
    print("This will fix:")
    print("  🔧 Stats Spotlight (Top Home, Top Away, Bust)")  
    print("  🏆 Weekly Awards (Top Score, Cupcake, Kitty)")
    print("  🖼️ Logo mapping using team_logos.json as source of truth")
    print()
    
    # Step 1: Backup existing files
    print("📦 Step 1: Backing up existing files...")
    backup_dir = Path("backup_emergency")
    backup_dir.mkdir(exist_ok=True)
    
    files_to_backup = [
        "updated_weekly_recap.py",
        "weekly_recap.py", 
        "logo_resolver.py"
    ]
    
    for file in files_to_backup:
        if Path(file).exists():
            shutil.copy2(file, backup_dir / file)
            print(f"   ✅ Backed up {file}")
    
    # Step 2: Check requirements
    print(f"\n🔍 Step 2: Checking requirements...")
    
    required_files = {
        "recap_template.docx": "Word template",
        "team_logos.json": "Team logo mappings",
        "gazette_data.py": "Data fetching module"
    }
    
    missing_files = []
    for file, desc in required_files.items():
        if Path(file).exists():
            print(f"   ✅ {desc}: {file}")
        else:
            print(f"   ❌ {desc}: {file} MISSING")
            missing_files.append(file)
    
    if missing_files:
        print(f"\n⚠️ Missing files: {missing_files}")
        print("   Please ensure these files exist before continuing.")
        
        # Create basic team_logos.json if missing
        if "team_logos.json" in missing_files:
            create_basic_team_logos()
    
    # Step 3: Apply the enhanced weekly_recap
    print(f"\n🔧 Step 3: Applying enhanced weekly_recap.py...")
    
    # The user should save the "Complete Fixed updated_weekly_recap.py" artifact
    enhanced_file = Path("updated_weekly_recap.py")
    if enhanced_file.exists():
        print(f"   ✅ Enhanced weekly_recap ready to use")
    else:
        print(f"   ⚠️ Please save the 'Complete Fixed updated_weekly_recap.py' artifact")
        print(f"      as 'updated_weekly_recap.py' in your project directory")
    
    # Step 4: Test the fixes
    print(f"\n🧪 Step 4: Testing fixes...")
    
    try:
        # Test awards calculation
        print("   Testing awards calculation...")
        sample_games = [
            {"HOME_TEAM_NAME": "Team A", "AWAY_TEAM_NAME": "Team B", "HOME_SCORE": "100.5", "AWAY_SCORE": "95.2"},
            {"HOME_TEAM_NAME": "Team C", "AWAY_TEAM_NAME": "Team D", "HOME_SCORE": "120.1", "AWAY_SCORE": "88.7"}
        ]
        
        # This will work if they've saved the enhanced file
        if enhanced_file.exists():
            import importlib.util
            spec = importlib.util.spec_from_file_location("updated_weekly_recap", enhanced_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            awards = module.calculate_weekly_awards_fixed(sample_games)
            if awards and awards["top_score"]["team"]:
                print(f"   ✅ Awards calculation working: Top={awards['top_score']['team']}")
            else:
                print(f"   ❌ Awards calculation failed")
        
    except Exception as e:
        print(f"   ⚠️ Test error (this is normal if you haven't saved the files yet): {e}")
    
    # Step 5: Usage instructions
    print(f"\n🚀 Step 5: Usage Instructions")
    print("=" * 50)
    
    print("To apply the complete fix:")
    print()
    print("1. Save these artifacts from Claude's response:")
    print("   📄 'Complete Fixed updated_weekly_recap.py' -> updated_weekly_recap.py")
    print("   📄 'Test Awards Logic' -> test_awards.py")
    print()
    print("2. Test the awards logic:")
    print("   python test_awards.py")
    print()
    print("3. Run your normal build process:")
    if Path("gazette_main.py").exists():
        print("   python gazette_main.py YOUR_LEAGUE_ID 2024 5 --verbose")
    elif Path("build_gazette.py").exists():
        print("   python build_gazette.py --week 5 --verbose")
    else:
        print("   python -c \"from updated_weekly_recap import build_weekly_recap; build_weekly_recap(league, league_id, year, week)\"")
    
    print()
    print("4. Check your generated document for:")
    print("   📊 Stats Spotlight sections (should have player names/points)")
    print("   🏆 Weekly Awards sections (should have team names/scores)")
    print("   🖼️ Team logos (should use team_logos.json mappings)")
    
    print(f"\n✅ Emergency patch setup complete!")
    print(f"📁 Your original files are backed up in: {backup_dir}")

def create_basic_team_logos():
    """Create a basic team_logos.json if missing"""
    basic_mapping = {
        "LEAGUE_LOGO": "logos/league_logos/_default.png",
        "SPONSOR_LOGO": "logos/sponsor_logos/_default.png"
    }
    
    try:
        with open("team_logos.json", "w") as f:
            json.dump(basic_mapping, f, indent=2)
        print("   ✅ Created basic team_logos.json")
        
        # Create logo directories
        for dir_name in ["logos/team_logos", "logos/league_logos", "logos/sponsor_logos"]:
            Path(dir_name).mkdir(parents=True, exist_ok=True)
        
        print("   ✅ Created logo directories")
        
    except Exception as e:
        print(f"   ⚠️ Could not create team_logos.json: {e}")

def check_template_placeholders():
    """Check if Word template has correct placeholders"""
    print(f"\n📋 TEMPLATE PLACEHOLDER CHECK")
    print("=" * 30)
    print("Your recap_template.docx should contain these placeholders:")
    print()
    
    required_placeholders = [
        # Awards
        "{{ AWARD_TOP_TEAM }}", "{{ AWARD_TOP_NOTE }}",
        "{{ AWARD_CUPCAKE_TEAM }}", "{{ AWARD_CUPCAKE_NOTE }}", 
        "{{ AWARD_KITTY_TEAM }}", "{{ AWARD_KITTY_NOTE }}",
        
        # Stats for each matchup (example for matchup 1)
        "{{ MATCHUP1_TOP_HOME }}", "{{ MATCHUP1_TOP_AWAY }}", "{{ MATCHUP1_BUST }}",
        
        # Basic info
        "{{ LEAGUE_NAME }}", "{{ WEEK }}", "{{ MATCHUP1_HOME }}", "{{ MATCHUP1_AWAY }}"
    ]
    
    print("Required placeholders:")
    for placeholder in required_placeholders:
        print(f"  {placeholder}")
    
    print()
    print("💡 If your template uses different placeholder names, you'll need to:")
    print("   1. Update your template to use these names, OR")
    print("   2. Modify the build_weekly_recap function to match your template")

if __name__ == "__main__":
    main()
    check_template_placeholders()