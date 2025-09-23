#!/usr/bin/env python3
"""
Enhanced logo_resolver.py — robust logo lookup with fuzzy matching & JSON mappings
Improved error handling and fallback mechanisms
"""

import json
import re
import unicodedata
import logging
from pathlib import Path
from functools import lru_cache
from typing import Optional, Dict, Any

# Set up logging
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
LOGOS_DIR = BASE_DIR / "logos"
TEAM_LOGOS_DIR = LOGOS_DIR / "team_logos"
LEAGUE_LOGOS_DIR = LOGOS_DIR / "league_logos"
SPONSOR_LOGOS_DIR = LOGOS_DIR / "sponsor_logos"

TEAM_LOGOS_JSON = BASE_DIR / "team_logos.json"
LEAGUE_LOGOS_JSON = BASE_DIR / "league_logos.json"
SPONSOR_LOGOS_JSON = BASE_DIR / "sponsor_logos.json"

PREFERRED_EXTS = [".png", ".jpg", ".jpeg"]
ALL_EXTS = PREFERRED_EXTS + [".webp", ".gif", ".bmp", ".svg"]

def _norm(s: str) -> str:
    """Normalize string for comparison"""
    try:
        if not s:
            return ""
        s = unicodedata.normalize("NFKC", str(s)).strip().lower()
        s = re.sub(r"[^\w\s-]", "", s)
        s = re.sub(r"\s+", " ", s)
        return s
    except Exception as e:
        logger.debug(f"Error normalizing string '{s}': {e}")
        return ""

def _safe_name(s: str) -> str:
    """Create safe filename from string"""
    try:
        if not s:
            return "unknown"
        s = _norm(s).replace(" ", "_")
        result = re.sub(r"[^\w-]", "", s)
        return result if result else "unknown"
    except Exception as e:
        logger.debug(f"Error creating safe name from '{s}': {e}")
        return "unknown"

@lru_cache(maxsize=3)
def _load_map(p: Path) -> Dict[str, str]:
    """Load JSON mapping with error handling"""
    if not p.exists():
        logger.debug(f"Mapping file not found: {p}")
        return {}
    
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        # Normalize keys for better matching
        normalized = {}
        for k, v in raw.items():
            if k and v:  # Skip empty keys/values
                normalized[_norm(k)] = v
                normalized[k] = v  # Keep original key too
        logger.debug(f"Loaded {len(normalized)} mappings from {p}")
        return normalized
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in {p}: {e}")
        return {}
    except Exception as e:
        logger.warning(f"Error loading mapping from {p}: {e}")
        return {}

def _ensure_directory_exists(logo_dir: Path) -> None:
    """Ensure logo directory exists"""
    try:
        logo_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create directory {logo_dir}: {e}")

def _find_logo_file(name: str, logo_dir: Path) -> Optional[str]:
    """Find logo file by various naming strategies"""
    if not name:
        return None
    
    safe = _safe_name(name)
    if not safe or safe == "unknown":
        return None
    
    # Generate filename variants
    variants = [
        safe,
        safe.replace("_s_", "s_"),
        safe.replace("_", ""),
        safe.replace("-", "_"),
        safe.replace("-", "")
    ]
    
    # Remove duplicates while preserving order
    seen = set()
    unique_variants = []
    for v in variants:
        if v not in seen and v:
            seen.add(v)
            unique_variants.append(v)
    
    # Search with preferred extensions first
    for variant in unique_variants:
        for ext in PREFERRED_EXTS:
            path = logo_dir / f"{variant}{ext}"
            if path.exists():
                logger.debug(f"Found logo: {path}")
                return str(path)
    
    # Search with all extensions
    for variant in unique_variants:
        for ext in ALL_EXTS:
            path = logo_dir / f"{variant}{ext}"
            if path.exists():
                logger.debug(f"Found logo: {path}")
                return str(path)
    
    return None

def _fuzzy_search_logos(name: str, logo_dir: Path) -> Optional[str]:
    """Perform fuzzy search in logo directory"""
    if not name or not logo_dir.exists():
        return None
    
    norm_name = _norm(name)
    if not norm_name:
        return None
    
    try:
        # Get all image files in directory
        image_files = []
        for ext in ALL_EXTS:
            image_files.extend(logo_dir.glob(f"*{ext}"))
        
        # Score each file based on similarity
        best_match = None
        best_score = 0
        
        for file_path in image_files:
            stem = _norm(file_path.stem)
            if not stem:
                continue
            
            # Calculate similarity score
            score = 0
            
            # Exact match gets highest score
            if stem == norm_name:
                score = 100
            # Substring match
            elif norm_name in stem or stem in norm_name:
                score = 80
            # Word overlap
            else:
                name_words = set(norm_name.split())
                stem_words = set(stem.split())
                if name_words and stem_words:
                    overlap = len(name_words & stem_words)
                    total = len(name_words | stem_words)
                    score = (overlap / total) * 60 if total > 0 else 0
            
            if score > best_score and score >= 60:  # Minimum threshold
                best_score = score
                best_match = file_path
        
        if best_match:
            logger.debug(f"Fuzzy match for '{name}': {best_match} (score: {best_score})")
            return str(best_match)
            
    except Exception as e:
        logger.debug(f"Error in fuzzy search for '{name}': {e}")
    
    return None

def _get_default_logo(logo_dir: Path, default_name: str = "_default.png") -> Optional[str]:
    """Get default logo with fallbacks"""
    _ensure_directory_exists(logo_dir)
    
    # Try the specified default
    default_path = logo_dir / default_name
    if default_path.exists():
        return str(default_path)
    
    # Try other common default names
    fallback_defaults = ["default.png", "logo.png", "unknown.png", "_placeholder.png"]
    for fallback in fallback_defaults:
        fallback_path = logo_dir / fallback
        if fallback_path.exists():
            logger.debug(f"Using fallback default: {fallback_path}")
            return str(fallback_path)
    
    # Try to find any image in the directory
    try:
        for ext in PREFERRED_EXTS:
            for img_file in logo_dir.glob(f"*{ext}"):
                logger.warning(f"Using arbitrary logo as fallback: {img_file}")
                return str(img_file)
    except Exception as e:
        logger.debug(f"Error searching for fallback logo: {e}")
    
    logger.warning(f"No default logo found in {logo_dir}")
    return None

def _find(name: str, logo_dir: Path, mapping: Dict[str, str], default_name: str = "_default.png") -> Optional[str]:
    """Enhanced logo finder with comprehensive fallback strategy"""
    
    if not name or not name.strip():
        logger.debug("Empty name provided to _find")
        return _get_default_logo(logo_dir, default_name)
    
    name = name.strip()
    _ensure_directory_exists(logo_dir)
    norm = _norm(name)
    
    logger.debug(f"Looking for logo: '{name}' (normalized: '{norm}')")
    
    # 1) Direct mapping lookup (original key)
    if name in mapping:
        path = BASE_DIR / mapping[name]
        if path.exists():
            logger.debug(f"Found via direct mapping: {path}")
            return str(path)
        else:
            logger.debug(f"Mapped path doesn't exist: {path}")
    
    # 2) Normalized mapping lookup
    if norm and norm in mapping:
        path = BASE_DIR / mapping[norm]
        if path.exists():
            logger.debug(f"Found via normalized mapping: {path}")
            return str(path)
        else:
            logger.debug(f"Normalized mapped path doesn't exist: {path}")
    
    # 3) Direct filename search
    logo_path = _find_logo_file(name, logo_dir)
    if logo_path:
        return logo_path
    
    # 4) Fuzzy search
    fuzzy_path = _fuzzy_search_logos(name, logo_dir)
    if fuzzy_path:
        return fuzzy_path
    
    # 5) Default logo
    default_path = _get_default_logo(logo_dir, default_name)
    if default_path:
        logger.debug(f"Using default logo for '{name}': {default_path}")
        return default_path
    
    logger.warning(f"No logo found for '{name}' in {logo_dir}")
    return None

def team_logo(name: str) -> Optional[str]:
    """Get team logo with enhanced error handling"""
    try:
        result = _find(name, TEAM_LOGOS_DIR, _load_map(TEAM_LOGOS_JSON), "_default.png")
        if not result:
            logger.warning(f"No team logo found for: {name}")
        return result
    except Exception as e:
        logger.error(f"Error getting team logo for '{name}': {e}")
        return _get_default_logo(TEAM_LOGOS_DIR)

def league_logo(name: str) -> Optional[str]:
    """Get league logo with enhanced error handling"""
    try:
        result = _find(name, LEAGUE_LOGOS_DIR, _load_map(LEAGUE_LOGOS_JSON), "_default.png")
        if not result:
            logger.warning(f"No league logo found for: {name}")
        return result
    except Exception as e:
        logger.error(f"Error getting league logo for '{name}': {e}")
        return _get_default_logo(LEAGUE_LOGOS_DIR)

def sponsor_logo(name: str) -> Optional[str]:
    """Get sponsor logo with enhanced error handling"""
    try:
        result = _find(name, SPONSOR_LOGOS_DIR, _load_map(SPONSOR_LOGOS_JSON), "_default.png")
        if not result:
            logger.warning(f"No sponsor logo found for: {name}")
        return result
    except Exception as e:
        logger.error(f"Error getting sponsor logo for '{name}': {e}")
        return _get_default_logo(SPONSOR_LOGOS_DIR)

def create_default_logos():
    """Create minimal default logos if none exist"""
    from PIL import Image, ImageDraw, ImageFont
    
    for logo_dir, logo_type in [
        (TEAM_LOGOS_DIR, "TEAM"),
        (LEAGUE_LOGOS_DIR, "LEAGUE"), 
        (SPONSOR_LOGOS_DIR, "SPONSOR")
    ]:
        default_path = logo_dir / "_default.png"
        if not default_path.exists():
            try:
                _ensure_directory_exists(logo_dir)
                
                # Create a simple 200x200 default logo
                img = Image.new('RGB', (200, 200), color='#cccccc')
                draw = ImageDraw.Draw(img)
                
                # Try to add text
                try:
                    font = ImageFont.load_default()
                    text = logo_type
                    bbox = draw.textbbox((0, 0), text, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    x = (200 - text_width) // 2
                    y = (200 - text_height) // 2
                    draw.text((x, y), text, fill='#666666', font=font)
                except Exception:
                    # If text fails, just create a colored rectangle
                    draw.rectangle([50, 50, 150, 150], fill='#999999')
                
                img.save(default_path)
                logger.info(f"Created default logo: {default_path}")
                
            except Exception as e:
                logger.error(f"Failed to create default logo at {default_path}: {e}")

def validate_logo_setup() -> Dict[str, Any]:
    """Validate logo directory setup and return status"""
    status = {
        "directories": {},
        "mappings": {},
        "defaults": {},
        "recommendations": []
    }
    
    # Check directories
    for name, path in [
        ("base", BASE_DIR),
        ("logos", LOGOS_DIR),
        ("team_logos", TEAM_LOGOS_DIR),
        ("league_logos", LEAGUE_LOGOS_DIR),
        ("sponsor_logos", SPONSOR_LOGOS_DIR)
    ]:
        status["directories"][name] = {
            "exists": path.exists(),
            "path": str(path),
            "is_directory": path.is_dir() if path.exists() else False
        }
        if path.exists() and path.is_dir():
            try:
                file_count = len([f for f in path.iterdir() if f.is_file()])
                status["directories"][name]["file_count"] = file_count
            except Exception as e:
                status["directories"][name]["error"] = str(e)
    
    # Check mapping files
    for name, path in [
        ("team_logos", TEAM_LOGOS_JSON),
        ("league_logos", LEAGUE_LOGOS_JSON), 
        ("sponsor_logos", SPONSOR_LOGOS_JSON)
    ]:
        status["mappings"][name] = {
            "exists": path.exists(),
            "path": str(path),
            "valid_json": False,
            "entry_count": 0
        }
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                status["mappings"][name]["valid_json"] = True
                status["mappings"][name]["entry_count"] = len(data) if isinstance(data, dict) else 0
            except Exception as e:
                status["mappings"][name]["error"] = str(e)
    
    # Check for default logos
    for name, path in [
        ("team_default", TEAM_LOGOS_DIR / "_default.png"),
        ("league_default", LEAGUE_LOGOS_DIR / "_default.png"),
        ("sponsor_default", SPONSOR_LOGOS_DIR / "_default.png")
    ]:
        status["defaults"][name] = {
            "exists": path.exists(),
            "path": str(path)
        }
    
    # Generate recommendations
    if not LOGOS_DIR.exists():
        status["recommendations"].append("Create logos directory structure")
    
    missing_defaults = [k for k, v in status["defaults"].items() if not v["exists"]]
    if missing_defaults:
        status["recommendations"].append(f"Create default logos: {', '.join(missing_defaults)}")
    
    empty_dirs = [k for k, v in status["directories"].items() 
                  if v.get("exists") and v.get("file_count", 0) == 0 and k.endswith("_logos")]
    if empty_dirs:
        status["recommendations"].append(f"Add logo files to: {', '.join(empty_dirs)}")
    
    return status

# Initialize default logos if needed
if __name__ == "__main__":
    print("Validating logo setup...")
    status = validate_logo_setup()
    
    print("\nStatus Summary:")
    for category, items in status.items():
        if category != "recommendations":
            print(f"\n{category.title()}:")
            for name, info in items.items():
                print(f"  {name}: {info}")
    
    if status["recommendations"]:
        print(f"\nRecommendations:")
        for rec in status["recommendations"]:
            print(f"  - {rec}")
        
        # Offer to create defaults
        try:
            response = input("\nCreate default logos? (y/n): ").strip().lower()
            if response == 'y':
                create_default_logos()
                print("Default logos created.")
        except KeyboardInterrupt:
            print("\nSkipped creating default logos.")