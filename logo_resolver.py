#!/usr/bin/env python3
"""
logo_resolver.py - Unified logo resolution for all gazette components
Consolidates logic from assets_fix.py, mascots_util.py, and gazette_helpers.py
"""

import json
import re
import unicodedata
from pathlib import Path
from functools import lru_cache
from typing import Optional, Dict

# Base paths
BASE_DIR = Path(__file__).resolve().parent
LOGOS_DIR = BASE_DIR / "logos"
TEAM_LOGOS_DIR = LOGOS_DIR / "team_logos"
LEAGUE_LOGOS_DIR = LOGOS_DIR / "league_logos"
SPONSOR_LOGOS_DIR = LOGOS_DIR / "sponsor_logos"

# Mapping files
TEAM_LOGOS_JSON = BASE_DIR / "team_logos.json"
LEAGUE_LOGOS_JSON = BASE_DIR / "league_logos.json"
SPONSOR_LOGOS_JSON = BASE_DIR / "sponsor_logos.json"

# Supported extensions (in priority order)
PREFERRED_EXTS = [".png", ".jpg", ".jpeg"]
ALL_EXTS = PREFERRED_EXTS + [".webp", ".gif", ".bmp", ".svg"]


def normalize_key(s: str) -> str:
    """Normalize a string for fuzzy matching"""
    # Handle Unicode normalization (curly quotes, etc.)
    s = unicodedata.normalize("NFKC", s)
    # Convert to lowercase
    s = s.strip().lower()
    # Remove special characters but keep spaces
    s = re.sub(r"[^\w\s-]", "", s)
    # Collapse multiple spaces
    s = re.sub(r"\s+", " ", s)
    return s


def sanitize_filename(s: str) -> str:
    """Convert string to safe filename"""
    s = normalize_key(s)
    # Replace spaces with underscores
    s = s.replace(" ", "_")
    # Remove any remaining unsafe characters
    s = re.sub(r"[^\w-]", "", s)
    return s


@lru_cache(maxsize=3)
def load_mapping(mapping_file: Path) -> Dict[str, str]:
    """Load and cache a JSON mapping file"""
    if not mapping_file.exists():
        return {}
    
    try:
        raw = json.loads(mapping_file.read_text(encoding="utf-8"))
        # Normalize keys for lookup
        return {normalize_key(k): v for k, v in raw.items()}
    except Exception as e:
        print(f"[logo] Error loading {mapping_file}: {e}")
        return {}


def find_logo_in_dir(
    name: str,
    logo_dir: Path,
    mapping: Dict[str, str],
    default_name: str = "_default.png"
) -> Optional[str]:
    """
    Find a logo using multiple strategies:
    1. Check JSON mapping (exact match)
    2. Check JSON mapping (normalized key match)  
    3. Scan directory for filename match
    4. Return default if available
    """
    if not logo_dir.exists():
        logo_dir.mkdir(parents=True, exist_ok=True)
    
    norm_name = normalize_key(name)
    
    # Strategy 1: Direct mapping lookup
    if name in mapping:
        path = BASE_DIR / mapping[name]
        if path.exists():
            return str(path)
    
    # Strategy 2: Normalized key match
    if norm_name in mapping:
        path = BASE_DIR / mapping[norm_name]
        if path.exists():
            return str(path)
    
    # Strategy 3: Filename search with variants
    safe_name = sanitize_filename(name)
    variants = [
        safe_name,
        safe_name.replace("_s_", "s_"),  # "nana_s_hawks" -> "nanas_hawks"
        safe_name.replace("_", ""),      # Remove all underscores
    ]
    
    # Try preferred extensions first
    for variant in variants:
        for ext in PREFERRED_EXTS:
            path = logo_dir / f"{variant}{ext}"
            if path.exists():
                return str(path)
    
    # Try all extensions
    for variant in variants:
        for ext in ALL_EXTS:
            path = logo_dir / f"{variant}{ext}"
            if path.exists():
                return str(path)
    
    # Strategy 4: Fuzzy search in directory
    for file in logo_dir.glob("*"):
        if file.suffix.lower() not in ALL_EXTS:
            continue
        
        file_norm = normalize_key(file.stem)
        if norm_name in file_norm or file_norm in norm_name:
            return str(file)
    
    # Strategy 5: Default fallback
    default_path = logo_dir / default_name
    if default_path.exists():
        print(f"[logo] Using default for '{name}': {default_path}")
        return str(default_path)
    
    print(f"[logo] No logo found for '{name}'")
    return None


def team_logo(name: str) -> Optional[str]:
    """Find team logo"""
    mapping = load_mapping(TEAM_LOGOS_JSON)
    return find_logo_in_dir(name, TEAM_LOGOS_DIR, mapping, "_default.png")


def league_logo(name: str) -> Optional[str]:
    """Find league logo"""
    mapping = load_mapping(LEAGUE_LOGOS_JSON)
    return find_logo_in_dir(name, LEAGUE_LOGOS_DIR, mapping, "_default.png")


def sponsor_logo(name: str) -> Optional[str]:
    """Find sponsor logo"""
    mapping = load_mapping(SPONSOR_LOGOS_JSON)
    return find_logo_in_dir(name, SPONSOR_LOGOS_DIR, mapping, "_default.png")


def update_mapping(mapping_file: Path, name: str, path: str) -> None:
    """Add or update a mapping entry"""
    # Load existing mapping (denormalized)
    existing = {}
    if mapping_file.exists():
        try:
            existing = json.loads(mapping_file.read_text(encoding="utf-8"))
        except:
            pass
    
    # Update with exact name (not normalized)
    existing[name] = path
    
    # Save
    mapping_file.parent.mkdir(parents=True, exist_ok=True)
    mapping_file.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def validate_mappings() -> Dict[str, int]:
    """Validate all mapping files and return stats"""
    stats = {"team": 0, "league": 0, "sponsor": 0, "missing": 0}
    
    for name, mapping_file, logo_dir in [
        ("team", TEAM_LOGOS_JSON, TEAM_LOGOS_DIR),
        ("league", LEAGUE_LOGOS_JSON, LEAGUE_LOGOS_DIR),
        ("sponsor", SPONSOR_LOGOS_JSON, SPONSOR_LOGOS_DIR),
    ]:
        if not mapping_file.exists():
            continue
        
        try:
            mapping = json.loads(mapping_file.read_text(encoding="utf-8"))
            stats[name] = len(mapping)
            
            for key, path in mapping.items():
                full_path = BASE_DIR / path
                if not full_path.exists():
                    print(f"[validate] Missing: {key} -> {path}")
                    stats["missing"] += 1
        except Exception as e:
            print(f"[validate] Error reading {mapping_file}: {e}")
    
    return stats


if __name__ == "__main__":
    # Test the resolver
    print("=== Logo Resolver Test ===\n")
    
    test_cases = [
        ("Nana's Hawks", team_logo),
        ("Phoenix Blues", team_logo),
        ("BrownSeaKC", league_logo),
        ("Gridiron Gazette", sponsor_logo),
    ]
    
    for name, resolver in test_cases:
        path = resolver(name)
        status = "✅" if path and Path(path).exists() else "❌"
        print(f"{status} {name}: {path}")
    
    print("\n=== Validation ===\n")
    stats = validate_mappings()
    print(f"Team logos: {stats['team']}")
    print(f"League logos: {stats['league']}")
    print(f"Sponsor logos: {stats['sponsor']}")
    print(f"Missing files: {stats['missing']}")