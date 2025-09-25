from __future__ import annotations
import json
import os
import re
import logging
from pathlib import Path
from typing import Dict, Optional

log = logging.getLogger("logo_resolver")

# --- Config / locations ---
TEAM_LOGOS_FILE = os.getenv("TEAM_LOGOS_FILE", "team_logos.json")
LEAGUE_LOGOS_FILE = os.getenv("LEAGUE_LOGOS_FILE", "league_logos.json")
SPONSOR_LOGOS_FILE = os.getenv("SPONSOR_LOGOS_FILE", "sponsor_logos.json")

# Primary logo directory
LOGO_DIRS = [
    Path("./logos/team_logos"),
    Path("logos/team_logos"),
    Path("logos/generated_logos"),
    Path("logos"),
]

DEFAULT_TEAM_LOGO = Path("logos/_default.png")
DEFAULT_LEAGUE_DIR = Path("logos/league_logos")
DEFAULT_SPONSOR_DIR = Path("logos/sponsor_logos")

def _load_json(path: Path) -> Dict[str, str]:
    """Load JSON file with error handling"""
    if not path.exists():
        log.debug(f"JSON file not found: {path}")
        return {}
    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content) or {}
        log.debug(f"Loaded {len(data)} entries from {path}")
        return data
    except Exception as e:
        log.warning(f"Failed to load JSON from {path}: {e}")
        return {}

def _norm(s: str) -> str:
    """Normalize team name for matching - aggressive character removal"""
    if not s:
        return ""
    s = str(s).lower().strip()
    
    # Remove ALL special characters (emojis, punctuation, etc.) - keep only letters, numbers, spaces
    s = re.sub(r"[^a-zA-Z0-9\s]", "", s)  # Remove everything except alphanumeric and spaces
    s = re.sub(r"\s+", "_", s)            # Replace spaces with underscores
    s = re.sub(r"_+", "_", s)             # Collapse multiple underscores
    s = s.strip("_")                      # Remove leading/trailing underscores
    
    return s

def _build_filesystem_logo_map() -> Dict[str, str]:
    """Build a comprehensive map of all available logos in the filesystem"""
    logo_map = {}
    
    # Scan the primary logos directory
    primary_dir = Path("./logos/team_logos")
    if primary_dir.exists():
        log.info(f"Scanning logo directory: {primary_dir}")
        
        for logo_file in primary_dir.glob("*.*"):
            if logo_file.is_file() and logo_file.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg']:
                # Create multiple possible team name variations for this logo
                base_name = logo_file.stem
                
                # Direct filename mapping
                logo_map[_norm(base_name)] = str(logo_file)
                
                # Common variations
                variations = [
                    base_name.replace("_", " "),           # "Team_Name" -> "Team Name"
                    base_name.replace("_", ""),            # "Team_Name" -> "TeamName"  
                    base_name.replace("-", " "),           # "Team-Name" -> "Team Name"
                    base_name.replace("-", ""),            # "Team-Name" -> "TeamName"
                    base_name.replace(".", " "),           # "Team.Name" -> "Team Name"
                    base_name.replace(".", ""),            # "Team.Name" -> "TeamName"
                ]
                
                for variation in variations:
                    norm_var = _norm(variation)
                    if norm_var and norm_var not in logo_map:
                        logo_map[norm_var] = str(logo_file)
                
                log.debug(f"Mapped logo: {base_name} -> {logo_file}")
        
        log.info(f"Built filesystem logo map with {len(logo_map)} mappings")
    else:
        log.warning(f"Logo directory not found: {primary_dir}")
    
    return logo_map

def _fuzzy_match_logo(team_name: str, logo_map: Dict[str, str]) -> Optional[str]:
    """Find the best logo match for a team name"""
    if not team_name:
        return None
        
    norm_team = _norm(team_name)
    if not norm_team:
        return None
    
    # 1. Exact match
    if norm_team in logo_map:
        log.debug(f"Exact logo match: '{team_name}' -> {logo_map[norm_team]}")
        return logo_map[norm_team]
    
    # 2. Substring matches (both directions)
    for logo_key, logo_path in logo_map.items():
        if norm_team in logo_key or logo_key in norm_team:
            log.debug(f"Substring logo match: '{team_name}' -> '{logo_key}' -> {logo_path}")
            return logo_path
    
    # 3. Word-level matching for multi-word team names
    team_words = set(norm_team.split("_"))
    if len(team_words) > 1:
        best_match = None
        best_score = 0
        
        for logo_key, logo_path in logo_map.items():
            logo_words = set(logo_key.split("_"))
            common_words = team_words.intersection(logo_words)
            if common_words:
                score = len(common_words) / max(len(team_words), len(logo_words))
                if score > best_score and score > 0.4:  # At least 40% word overlap
                    best_match = logo_path
                    best_score = score
        
        if best_match:
            log.debug(f"Word-level logo match: '{team_name}' -> {best_match} (score: {best_score:.2f})")
            return best_match
    
    return None

# Cache the filesystem logo map
_FILESYSTEM_LOGO_MAP: Optional[Dict[str, str]] = None

def _get_filesystem_logo_map() -> Dict[str, str]:
    """Get cached filesystem logo map"""
    global _FILESYSTEM_LOGO_MAP
    if _FILESYSTEM_LOGO_MAP is None:
        _FILESYSTEM_LOGO_MAP = _build_filesystem_logo_map()
    return _FILESYSTEM_LOGO_MAP

def team_logo(team_name: str) -> Optional[str]:
    """Get team logo path - prioritize JSON mapping over filesystem scanning"""
    if not team_name:
        return str(DEFAULT_TEAM_LOGO) if DEFAULT_TEAM_LOGO.exists() else None
    
    log.debug(f"Looking for team logo: '{team_name}'")
    
    # 1. PRIORITIZE JSON mapping - use exact team names as keys
    try:
        data = _load_json(Path(TEAM_LOGOS_FILE))
        if data:
            # Direct exact match first
            if team_name in data:
                json_path = data[team_name]
                if Path(json_path).exists():
                    log.info(f"JSON exact match: '{team_name}' -> {json_path}")
                    return str(Path(json_path))
            
            # Handle hierarchical structure if present
            if not all(isinstance(v, str) for v in data.values()):
                league_id = os.getenv("LEAGUE_ID", "")
                league_name = os.getenv("LEAGUE_DISPLAY_NAME") or os.getenv("LEAGUE_NAME", "")
                
                # Check default section
                default_map = data.get("default", {})
                if isinstance(default_map, dict) and team_name in default_map:
                    json_path = default_map[team_name]
                    if Path(json_path).exists():
                        log.info(f"JSON default match: '{team_name}' -> {json_path}")
                        return str(Path(json_path))
                
                # Check league-specific sections
                leagues = data.get("leagues", {})
                if isinstance(leagues, dict):
                    if league_id and league_id in leagues:
                        league_data = leagues[league_id]
                        if isinstance(league_data, dict) and team_name in league_data:
                            json_path = league_data[team_name]
                            if Path(json_path).exists():
                                log.info(f"JSON league ID match: '{team_name}' -> {json_path}")
                                return str(Path(json_path))
                    
                    if league_name and league_name in leagues:
                        league_data = leagues[league_name]
                        if isinstance(league_data, dict) and team_name in league_data:
                            json_path = league_data[team_name]
                            if Path(json_path).exists():
                                log.info(f"JSON league name match: '{team_name}' -> {json_path}")
                                return str(Path(json_path))
            
    except Exception as e:
        log.warning(f"JSON lookup failed for '{team_name}': {e}")
    
    # 2. Fallback to filesystem scanning (only if JSON fails)
    log.debug(f"JSON lookup failed, trying filesystem for: '{team_name}'")
    filesystem_map = _get_filesystem_logo_map()
    logo_path = _fuzzy_match_logo(team_name, filesystem_map)
    if logo_path and Path(logo_path).exists():
        log.info(f"Filesystem fallback match: '{team_name}' -> {logo_path}")
        return logo_path
    
    # 3. Default fallback
    if DEFAULT_TEAM_LOGO.exists():
        log.warning(f"Using default logo for: '{team_name}'")
        return str(DEFAULT_TEAM_LOGO)
    
    log.error(f"No logo found for team: '{team_name}'")
    return None

def league_logo(name: Optional[str] = None) -> Optional[str]:
    """Get league logo path"""
    league_name = name or os.getenv("LEAGUE_DISPLAY_NAME") or os.getenv("LEAGUE_NAME") or ""
    
    # Check for brownseakc.png specifically
    possible_paths = [
        Path("./logos/team_logos/brownseakc.png"),
        Path("logos/team_logos/brownseakc.png"),
        Path("logos/league_logos/brownseakc.png"),
        Path("logos/brownseakc.png"),
    ]
    
    for path in possible_paths:
        if path.exists():
            log.debug(f"Found league logo: {path}")
            return str(path)
    
    # Fallback to JSON mapping
    return _find_brand_logo(league_name, LEAGUE_LOGOS_FILE, DEFAULT_LEAGUE_DIR)

def sponsor_logo(name: Optional[str] = None) -> Optional[str]:
    """Get sponsor logo path"""
    sponsor_name = name or os.getenv("SPONSOR_NAME") or "Gridiron Gazette"
    return _find_brand_logo(sponsor_name, SPONSOR_LOGOS_FILE, DEFAULT_SPONSOR_DIR)

def _find_brand_logo(display_name: str, json_file: str, default_dir: Path) -> Optional[str]:
    """Find brand logo with priority: JSON -> directory scan -> None"""
    if not display_name:
        return None
        
    nm = display_name.strip()
    slug = _norm(nm)
    mapping = _load_json(Path(json_file))

    log.debug(f"Looking for brand logo: '{nm}' -> '{slug}'")

    # 1. Direct key match in JSON
    if nm in mapping:
        rel = mapping[nm]
        if isinstance(rel, str) and Path(rel).exists():
            log.debug(f"Brand exact match: {nm} -> {rel}")
            return str(Path(rel))

    # 2. Fuzzy match in JSON
    for k, v in mapping.items():
        if _norm(k) == slug and isinstance(v, str) and Path(v).exists():
            log.debug(f"Brand fuzzy match: {nm} -> {v}")
            return str(Path(v))

    # 3. Scan default directory
    if default_dir.exists():
        exts = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"]
        for p in default_dir.glob("*.*"):
            if p.is_file() and p.suffix.lower() in exts:
                if _norm(p.stem) == slug:
                    log.debug(f"Brand directory match: {nm} -> {p}")
                    return str(p)

    log.debug(f"No brand logo found for: {nm}")
    return None

# --- Image sanitation for docx ---
try:
    from PIL import Image, UnidentifiedImageError
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    log.warning("PIL not available - logo sanitation disabled")

_CACHE_DIR = Path("logos/_cache")
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _sanitize_for_docx(img_path: str | Path) -> Optional[str]:
    """
    Open the image with Pillow and re-save as a proper PNG copy in logos/_cache.
    Returns path to sanitized PNG or None if it fails.
    """
    if not PIL_AVAILABLE:
        # If PIL not available, just return original path if it exists
        p = Path(img_path)
        return str(p) if p.exists() and p.is_file() else None
    
    try:
        p = Path(img_path)
        if not p.exists() or not p.is_file():
            return None
            
        out = _CACHE_DIR / (p.stem + ".png")
        
        # Skip if already sanitized and newer
        if out.exists() and out.stat().st_mtime >= p.stat().st_mtime:
            return str(out)
        
        with Image.open(p) as im:
            # Convert to compatible mode
            if im.mode not in ("RGB", "RGBA"):
                if "transparency" in im.info or im.mode == "P":
                    im = im.convert("RGBA")
                else:
                    im = im.convert("RGB")
            
            # Save as PNG
            im.save(out, format="PNG", optimize=True)
            log.debug(f"Sanitized logo: {p} -> {out}")
            
        return str(out)
        
    except Exception as e:
        log.warning(f"Failed to sanitize image {img_path}: {e}")
        # Return original if sanitization fails
        p = Path(img_path)
        return str(p) if p.exists() else None

def sanitize_logo_for_docx(path_str: Optional[str]) -> Optional[str]:
    """Sanitize logo for docx with error handling"""
    if not path_str:
        return None
    return _sanitize_for_docx(path_str)