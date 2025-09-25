#!/usr/bin/env python3
"""
Logo Diagnostic and Setup Tool for Gridiron Gazette
Helps identify missing logos and creates proper directory structure
"""

import os
import shutil
from pathlib import Path
from typing import Dict, List

def diagnose_logos():
    """Run complete logo diagnostic"""
    print("\n" + "="*60)
    print("GRIDIRON GAZETTE LOGO DIAGNOSTIC")
    print("="*60)
    
    # Teams from your Week 3 output
    teams_needed = [
        "Nana's Hawks",
        "The Champ Big Daddy",
        "Jimmy Birds",
        "Annie1235 slayy",
        "DEM BOY'S!🏆🏆🏆🏆",
        "Avondale Welders",
        "Phoenix Blues",
        "Kansas City Pumas",
        "🏉THE💀REBELS🏉",
        "Under the InfluWENTZ"
    ]
    
    # Expected logo filenames (multiple variations)
    team_mappings = {
        "Nana's Hawks": ["NanasHawks", "Nanas_Hawks", "nanashawks"],
        "The Champ Big Daddy": ["TheChampBigDaddy", "ChampBigDaddy", "BigDaddy"],
        "Jimmy Birds": ["JimmyBirds", "Jimmy_Birds", "jimmybirds"],
        "Annie1235 slayy": ["Annie1235slayy", "Annie1235_slayy", "annieslayy"],
        "DEM BOY'S!🏆🏆🏆🏆": ["DEMBOYS", "DEM_BOYS", "demboys"],
        "Avondale Welders": ["AvondaleWelders", "Avondale_Welders", "welders"],
        "Phoenix Blues": ["PhoenixBlues", "Phoenix_Blues", "phoenixblues"],
        "Kansas City Pumas": ["KansasCity_Pumas", "KansasCityPumas", "KC_Pumas"],
        "🏉THE💀REBELS🏉": ["THEREBELS", "THE_REBELS", "therebels", "THEREBELS_"],
        "Under the InfluWENTZ": ["UndertheInfluWENTZ", "Underthe_InfluWENTZ", "InfluWENTZ"]
    }
    
    # Check directory structure
    print("\n1. CHECKING DIRECTORY STRUCTURE:")
    print("-" * 40)
    
    required_dirs = [
        "logos",
        "logos/teamlogos",
        "logos/league_logos",
        "logos/sponsor_logos"
    ]
    
    missing_dirs = []
    for dir_path in required_dirs:
        path = Path(dir_path)
        if path.exists():
            file_count = len(list(path.glob("*.*")))
            print(f"  ✅ {dir_path:25} ({file_count} files)")
        else:
            print(f"  ❌ {dir_path:25} MISSING")
            missing_dirs.append(dir_path)
    
    # Create missing directories
    if missing_dirs:
        print("\n  Creating missing directories...")
        for dir_path in missing_dirs:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
            print(f"    ✅ Created {dir_path}")
    
    # Check for team logos
    print("\n2. CHECKING TEAM LOGOS:")
    print("-" * 40)
    
    found_logos = {}
    missing_logos = []
    
    for team, variations in team_mappings.items():
        found = False
        for variation in variations:
            for ext in ['.png', '.jpg', '.jpeg', '.gif']:
                # Check multiple locations
                paths_to_check = [
                    f"logos/teamlogos/{variation}{ext}",
                    f"logos/team_logos/{variation}{ext}",
                    f"logos/{variation}{ext}",
                    f"{variation}{ext}"
                ]
                
                for path_str in paths_to_check:
                    if Path(path_str).exists():
                        print(f"  ✅ {team:30} -> {path_str}")
                        found_logos[team] = path_str
                        found = True
                        break
                
                if found:
                    break
            if found:
                break
        
        if not found:
            print(f"  ❌ {team:30} -> NOT FOUND")
            missing_logos.append(team)
    
    # Check for Browns/League logo
    print("\n3. CHECKING LEAGUE LOGO (Browns):")
    print("-" * 40)
    
    browns_paths = [
        "logos/teamlogos/brownseakc.png",
        "logos/team_logos/brownseakc.png",
        "logos/league_logos/brownseakc.png",
        "logos/brownseakc.png",
        "brownseakc.png"
    ]
    
    browns_found = False
    for path in browns_paths:
        if Path(path).exists():
            print(f"  ✅ Browns logo found: {path}")
            browns_found = True
            break
    
    if not browns_found:
        print(f"  ❌ Browns logo NOT FOUND")
        print(f"     Expected in one of these locations:")
        for path in browns_paths:
            print(f"       - {path}")
    
    # Summary and recommendations
    print("\n" + "="*60)
    print("SUMMARY & RECOMMENDATIONS")
    print("="*60)
    
    if missing_logos:
        print("\n⚠️  MISSING LOGOS:")
        print("Create/add these logo files:")
        for team in missing_logos:
            suggested_name = team_mappings[team][0]
            print(f"  - logos/teamlogos/{suggested_name}.png")
    
    if not browns_found:
        print("\n⚠️  MISSING BROWNS LEAGUE LOGO:")
        print("  Add your league logo as: logos/teamlogos/brownseakc.png")
    
    if not missing_logos and browns_found:
        print("\n✅ ALL LOGOS FOUND! Your setup is complete.")
    else:
        print("\n📝 TO FIX:")
        print("1. Add the missing logo files to logos/teamlogos/")
        print("2. Use PNG format for best compatibility")
        print("3. Keep filenames simple (no spaces or special characters)")
        print("4. Run this diagnostic again to verify")
    
    # Create sample logo files if requested
    print("\n" + "="*60)
    response = input("Would you like to create placeholder logos for missing teams? (y/n): ")
    if response.lower() == 'y':
        create_placeholder_logos(missing_logos, team_mappings)


def create_placeholder_logos(missing_teams: List[str], mappings: Dict[str, List[str]]):
    """Create placeholder logo files for missing teams"""
    print("\nCreating placeholder logos...")
    
    # Ensure directory exists
    Path("logos/teamlogos").mkdir(parents=True, exist_ok=True)
    
    for team in missing_teams:
        if team in mappings:
            filename = f"logos/teamlogos/{mappings[team][0]}.png"
            
            # Create a simple placeholder PNG (1x1 pixel, transparent)
            # This is a minimal PNG file
            png_data = bytes([
                0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
                0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
                0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
                0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
                0x89, 0x00, 0x00, 0x00, 0x0D, 0x49, 0x44, 0x41,  # IDAT chunk
                0x54, 0x78, 0x9C, 0x62, 0x00, 0x01, 0x00, 0x00,
                0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,
                0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,  # IEND chunk
                0x42, 0x60, 0x82
            ])
            
            with open(filename, 'wb') as f:
                f.write(png_data)
            
            print(f"  ✅ Created placeholder: {filename}")
    
    print("\n📝 NOTE: These are 1x1 pixel placeholders.")
    print("   Replace them with actual team logos for best results!")


def organize_existing_logos():
    """Find and organize any existing logo files in the project"""
    print("\n" + "="*60)
    print("SEARCHING FOR EXISTING LOGO FILES")
    print("="*60)
    
    # Search for image files anywhere in the project
    image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.PNG', '.JPG']
    found_images = []
    
    for root, dirs, files in os.walk('.'):
        # Skip hidden directories and node_modules
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'node_modules']
        
        for file in files:
            if any(file.endswith(ext) for ext in image_extensions):
                path = Path(root) / file
                # Skip if already in logos directory
                if not str(path).startswith('logos'):
                    found_images.append(path)
    
    if found_images:
        print(f"\nFound {len(found_images)} image files outside logos directory:")
        for img_path in found_images[:20]:  # Show first 20
            print(f"  - {img_path}")
        
        if len(found_images) > 20:
            print(f"  ... and {len(found_images) - 20} more")
        
        response = input("\nWould you like to copy potential logo files to logos/teamlogos? (y/n): ")
        if response.lower() == 'y':
            copy_potential_logos(found_images)
    else:
        print("\nNo image files found outside logos directory.")


def copy_potential_logos(image_paths: List[Path]):
    """Copy potential logo files to the logos directory"""
    Path("logos/teamlogos").mkdir(parents=True, exist_ok=True)
    
    # Keywords that might indicate a logo
    logo_keywords = ['logo', 'team', 'badge', 'icon', 'hawks', 'birds', 'blues', 
                     'pumas', 'rebels', 'browns', 'champ', 'daddy', 'annie', 
                     'dem', 'boys', 'avondale', 'welders', 'phoenix', 'kansas']
    
    copied = 0
    for img_path in image_paths:
        filename = img_path.name.lower()
        if any(keyword in filename for keyword in logo_keywords):
            dest = Path("logos/teamlogos") / img_path.name
            if not dest.exists():
                shutil.copy2(img_path, dest)
                print(f"  ✅ Copied {img_path.name} to logos/teamlogos/")
                copied += 1
    
    if copied:
        print(f"\n✅ Copied {copied} potential logo files")
    else:
        print("\n No potential logo files found to copy")


if __name__ == "__main__":
    print("GRIDIRON GAZETTE LOGO DIAGNOSTIC TOOL")
    print("This tool will help identify and fix logo issues")
    
    # Run diagnostic
    diagnose_logos()
    
    # Offer to search for existing images
    print("\n" + "="*60)
    response = input("Would you like to search for existing image files in the project? (y/n): ")
    if response.lower() == 'y':
        organize_existing_logos()
    
    print("\n" + "="*60)
    print("DIAGNOSTIC COMPLETE")
    print("Run 'python build_gazette.py --week 3 --verbose' to test")
    print("="*60)