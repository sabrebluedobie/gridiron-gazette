#!/usr/bin/env python3
"""
Cross-platform fix for missing DEM BOY'S logo
Works on Windows, Mac, and Linux with proper Unicode handling
"""

import json
import sys
import platform
from pathlib import Path

def detect_platform():
    """Detect the current platform for debugging"""
    system = platform.system()
    print(f"[platform] Running on: {system} ({platform.platform()})")
    print(f"[platform] Python: {sys.version}")
    return system

def safe_read_json(file_path):
    """Safely read JSON file with proper encoding across platforms"""
    encodings_to_try = ['utf-8', 'utf-8-sig', 'cp1252', 'latin1']
    
    for encoding in encodings_to_try:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                data = json.load(f)
            print(f"[json] Successfully read {file_path} with {encoding} encoding")
            return data
        except UnicodeDecodeError:
            print(f"[json] Failed to read with {encoding} encoding, trying next...")
            continue
        except json.JSONDecodeError as e:
            print(f"[json] JSON decode error with {encoding}: {e}")
            continue
        except Exception as e:
            print(f"[json] Unexpected error with {encoding}: {e}")
            continue
    
    print(f"[json] ❌ Could not read {file_path} with any encoding")
    return {}

def safe_write_json(file_path, data):
    """Safely write JSON file with proper encoding across platforms"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[json] ✅ Successfully wrote {file_path}")
        return True
    except Exception as e:
        print(f"[json] ❌ Error writing {file_path}: {e}")
        return False

def find_logo_files(search_pattern="*DEM*"):
    """Find logo files matching pattern across platforms"""
    logo_dir = Path("logos/team_logos")
    
    if not logo_dir.exists():
        print(f"[search] ❌ Logo directory not found: {logo_dir}")
        return []
    
    print(f"[search] Searching for files matching '{search_pattern}' in {logo_dir}")
    
    # Case-insensitive search across platforms
    found_files = []
    
    try:
        # Get all files in directory
        all_files = list(logo_dir.iterdir())
        print(f"[search] Found {len(all_files)} total files in logo directory")
        
        # Search for DEM BOY'S related files
        search_terms = ['dem', 'boy', 'boys', 'DEM', 'BOY', 'BOYS']
        
        for file_path in all_files:
            if file_path.is_file():
                filename = file_path.name.lower()
                if any(term.lower() in filename for term in search_terms):
                    found_files.append(file_path)
                    print(f"[search] Found matching file: {file_path}")
        
    except Exception as e:
        print(f"[search] Error searching files: {e}")
    
    return found_files

def create_placeholder_logo(placeholder_path):
    """Create a cross-platform placeholder logo"""
    try:
        # Try to create PNG with PIL
        from PIL import Image, ImageDraw, ImageFont
        
        img = Image.new('RGBA', (200, 200), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Gold circle (cowboys theme)
        draw.ellipse([20, 20, 180, 180], fill=(212, 175, 55, 255))
        
        # Add text
        text = "DB"  # DEM BOYS initials
        
        # Try different font approaches across platforms
        font = None
        font_paths = [
            # Windows
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/Arial.ttf",
            # Mac
            "/System/Library/Fonts/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
            # Linux
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        ]
        
        for font_path in font_paths:
            try:
                if Path(font_path).exists():
                    font = ImageFont.truetype(font_path, 40)
                    print(f"[image] Using font: {font_path}")
                    break
            except:
                continue
        
        if not font:
            try:
                font = ImageFont.load_default()
                print("[image] Using default font")
            except:
                print("[image] No font available, using basic drawing")
        
        if font:
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = (200 - text_width) // 2
            y = (200 - text_height) // 2
            draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)
        
        img.save(placeholder_path, 'PNG')
        print(f"[image] ✅ Created PNG placeholder: {placeholder_path}")
        return str(placeholder_path)
        
    except ImportError:
        print("[image] PIL not available, creating text placeholder")
    except Exception as e:
        print(f"[image] Error creating PNG: {e}")
    
    # Fallback: create text placeholder
    try:
        text_path = placeholder_path.with_suffix('.txt')
        text_path.write_text("DEM BOY'S logo placeholder", encoding='utf-8')
        print(f"[image] ✅ Created text placeholder: {text_path}")
        return str(text_path)
    except Exception as e:
        print(f"[image] ❌ Could not create any placeholder: {e}")
        return None

def fix_dem_boys_logo():
    """Main function to fix the DEM BOY'S logo mapping"""
    print("=== Cross-Platform DEM BOY'S Logo Fix ===")
    
    # Detect platform
    system = detect_platform()
    
    # Load current mapping
    logo_file = Path("team_logos.json")
    print(f"[fix] Looking for: {logo_file.absolute()}")
    
    if logo_file.exists():
        logos = safe_read_json(logo_file)
        print(f"[fix] Loaded {len(logos)} existing logo mappings")
    else:
        print("[fix] team_logos.json not found, creating new mapping")
        logos = {}
    
    # The problematic team name
    team_name = "DEM BOY'S! 🏆🏆🏆🏆"
    current_mapping = logos.get(team_name, "NOT_FOUND")
    print(f"[fix] Current mapping for '{team_name}': {current_mapping}")
    
    # Check if current mapping works
    if current_mapping != "NOT_FOUND":
        current_path = Path(current_mapping)
        if current_path.exists():
            print(f"[fix] ✅ Current mapping is valid: {current_mapping}")
            return logos
        else:
            print(f"[fix] ❌ Current mapping points to missing file: {current_mapping}")
    
    # Search for existing files
    found_files = find_logo_files()
    
    if found_files:
        # Use the first found file
        chosen_file = found_files[0]
        logos[team_name] = str(chosen_file)
        print(f"[fix] ✅ Using existing file: {chosen_file}")
    else:
        # Create placeholder
        print("[fix] No existing files found, creating placeholder...")
        placeholder_dir = Path("logos/team_logos")
        placeholder_dir.mkdir(parents=True, exist_ok=True)
        
        placeholder_path = placeholder_dir / "DEM_BOYS.png"
        created_placeholder = create_placeholder_logo(placeholder_path)
        
        if created_placeholder:
            logos[team_name] = created_placeholder
            print(f"[fix] ✅ Created and mapped placeholder: {created_placeholder}")
        else:
            print("[fix] ❌ Could not create placeholder")
            return logos
    
    # Save updated mapping
    if safe_write_json(logo_file, logos):
        print(f"[fix] ✅ Updated logo mapping saved")
        print(f"[fix] Final mapping: '{team_name}' -> '{logos[team_name]}'")
    else:
        print("[fix] ❌ Failed to save updated mapping")
    
    return logos

def verify_fix():
    """Verify that the fix worked"""
    print("\n=== Verification ===")
    
    logo_file = Path("team_logos.json")
    if not logo_file.exists():
        print("[verify] ❌ team_logos.json still missing")
        return False
    
    logos = safe_read_json(logo_file)
    team_name = "DEM BOY'S! 🏆🏆🏆🏆"
    
    if team_name not in logos:
        print(f"[verify] ❌ {team_name} not found in mapping")
        return False
    
    mapped_file = logos[team_name]
    file_path = Path(mapped_file)
    
    if file_path.exists():
        print(f"[verify] ✅ Logo file exists: {mapped_file}")
        return True
    else:
        print(f"[verify] ❌ Mapped file missing: {mapped_file}")
        return False

def main():
    """Main execution function"""
    try:
        # Run the fix
        logos = fix_dem_boys_logo()
        
        # Verify it worked
        success = verify_fix()
        
        if success:
            print("\n🎉 Logo fix completed successfully!")
            print("You can now run your gazette build.")
        else:
            print("\n❌ Logo fix may have issues.")
            print("Check the output above for details.")
        
        return 0 if success else 1
        
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)