"""
Logo Resolver for Gridiron Gazette
Handles team, league, and sponsor logo resolution with fuzzy matching
"""

import os
import json
import logging
import re
from pathlib import Path
from typing import Dict, Optional, Tuple
from difflib import SequenceMatcher

log = logging.getLogger("logo_resolver")

# ================= Configuration =================

# Default paths
DEFAULT_LOGO_DIRS = [
    "./logos",
    "./logos/team_logos",
    "./logos/league_logos", 
    "./logos/sponsor_logos",
    "./media",
    "."
]

# Image extensions to search
IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp']

# ================= Utility Functions =================

def normalize_name(name: str) -> str:
    """
    Normalize a name for comparison
    - Lowercase
    - Remove special characters
    - Remove extra whitespace
    """
    if not name:
        return ""
    
    # Convert to lowercase
    normalized = name.lower()
    
    # Remove common emoji and special characters but keep alphanumeric
    normalized = re.sub(r'[^\w\s-]', '', normalized)
    
    # Replace multiple spaces with single space
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Remove leading/trailing whitespace
    normalized = normalized.strip()
    
    return normalized

def create_slug(name: str) -> str:
    """Create a slug version of the name for filename matching"""
    if not name:
        return ""
    
    slug = normalize_name(name)
    # Replace spaces with hyphens or underscores
    slug = re.sub(r'[\s]+', '-', slug)
    # Remove any remaining special characters
    slug = re.sub(r'[^a-z0-9-_]', '', slug)
    
    return slug

def fuzzy_match_score(str1: str, str2: str) -> float:
    """Calculate fuzzy match score between two strings (0-1)"""
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

# ================= Logo Finder =================

def find_logo_file(name: str, logo_type: str = "team") -> Optional[str]:
    """
    Find a logo file using various matching strategies
    
    Args:
        name: The name to search for
        logo_type: Type of logo ('team', 'league', 'sponsor')
    
    Returns:
        Path to the logo file if found, None otherwise
    """
    if not name:
        return None
    
    # Normalize the search name
    normalized = normalize_name(name)
    slug = create_slug(name)
    
    # Build list of possible filenames
    possible_names = [
        name,  # Original name
        normalized,  # Normalized version
        slug,  # Slug version
        normalized.replace(' ', '_'),  # Underscore version
        normalized.replace(' ', '-'),  # Hyphen version
        normalized.replace(' ', ''),  # No spaces version
    ]
    
    # Add variations without common suffixes
    for suffix in ['fc', 'team', 'logo', 'club']:
        for pname in list(possible_names):
            if pname.endswith(suffix):
                possible_names.append(pname[:-len(suffix)].strip())
    
    # Search directories based on logo type
    search_dirs = DEFAULT_LOGO_DIRS.copy()
    if logo_type == "league":
        search_dirs.insert(0, "./logos/league_logos")
    elif logo_type == "sponsor":
        search_dirs.insert(0, "./logos/sponsor_logos")
    else:  # team
        search_dirs.insert(0, "./logos/team_logos")
    
    # First pass: exact match
    for directory in search_dirs:
        if not os.path.exists(directory):
            continue
        
        for possible_name in possible_names:
            for ext in IMAGE_EXTENSIONS:
                # Try exact match
                filepath = os.path.join(directory, f"{possible_name}{ext}")
                if os.path.exists(filepath):
                    log.info(f"Found exact match logo: {filepath}")
                    return filepath
    
    # Second pass: fuzzy match
    best_match = None
    best_score = 0.7  # Minimum threshold
    
    for directory in search_dirs:
        if not os.path.exists(directory):
            continue
        
        try:
            for filename in os.listdir(directory):
                # Check if it's an image file
                if not any(filename.lower().endswith(ext) for ext in IMAGE_EXTENSIONS):
                    continue
                
                # Get filename without extension
                base_name = os.path.splitext(filename)[0]
                
                # Calculate match scores
                for possible_name in possible_names:
                    score = fuzzy_match_score(base_name, possible_name)
                    
                    if score > best_score:
                        best_score = score
                        best_match = os.path.join(directory, filename)
        except Exception as e:
            log.warning(f"Error scanning directory {directory}: {e}")
    
    if best_match:
        log.info(f"Found fuzzy match logo: {best_match} (score: {best_score:.2f})")
        return best_match
    
    log.warning(f"No logo found for '{name}' (type: {logo_type})")
    return None

# ================= JSON-based Logo Resolution =================

class LogoResolver:
    """Main logo resolver class using JSON configuration files"""
    
    def __init__(self, team_logos_file: str = "team_logos.json",
                 league_logos_file: str = "league_logos.json", 
                 sponsor_logos_file: str = "sponsor_logos.json"):
        """Initialize the logo resolver with JSON configuration files"""
        self.team_logos = self._load_json(team_logos_file)
        self.league_logos = self._load_json(league_logos_file)
        self.sponsor_logos = self._load_json(sponsor_logos_file)
        
        # Build normalized lookup maps
        self._build_lookup_maps()
    
    def _load_json(self, filepath: str) -> Dict:
        """Load a JSON configuration file"""
        if not os.path.exists(filepath):
            log.warning(f"Logo configuration file not found: {filepath}")
            return {}
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                log.info(f"Loaded {len(data)} entries from {filepath}")
                return data
        except Exception as e:
            log.error(f"Error loading {filepath}: {e}")
            return {}
    
    def _build_lookup_maps(self):
        """Build normalized lookup maps for faster matching"""
        self.team_lookup = {}
        self.league_lookup = {}
        self.sponsor_lookup = {}
        
        # Build team lookup with variations
        for team_name, logo_path in self.team_logos.items():
            normalized = normalize_name(team_name)
            self.team_lookup[normalized] = logo_path
            
            # Add slug version
            slug = create_slug(team_name)
            if slug != normalized:
                self.team_lookup[slug] = logo_path
            
            # Add version without spaces
            no_space = normalized.replace(' ', '')
            if no_space != normalized:
                self.team_lookup[no_space] = logo_path
        
        # Build league lookup
        for league_name, logo_path in self.league_logos.items():
            normalized = normalize_name(league_name)
            self.league_lookup[normalized] = logo_path
            self.league_lookup[create_slug(league_name)] = logo_path
        
        # Build sponsor lookup
        for sponsor_name, logo_path in self.sponsor_logos.items():
            normalized = normalize_name(sponsor_name)
            self.sponsor_lookup[normalized] = logo_path
            self.sponsor_lookup[create_slug(sponsor_name)] = logo_path
    
    def resolve_team_logo(self, team_name: str) -> Optional[str]:
        """Resolve a team logo path"""
        if not team_name:
            return None
        
        # First try direct lookup in JSON
        if team_name in self.team_logos:
            path = self.team_logos[team_name]
            if os.path.exists(path):
                log.info(f"Found team logo from JSON: {path}")
                return path
        
        # Try normalized lookup
        normalized = normalize_name(team_name)
        if normalized in self.team_lookup:
            path = self.team_lookup[normalized]
            if os.path.exists(path):
                log.info(f"Found team logo from normalized lookup: {path}")
                return path
        
        # Try filesystem search
        return find_logo_file(team_name, "team")
    
    def resolve_league_logo(self, league_name: str) -> Optional[str]:
        """Resolve a league logo path"""
        if not league_name:
            return None
        
        # Special case for common league names
        if "browns" in league_name.lower() or "brownseakc" in league_name.lower():
            # Direct path to your league logo
            special_path = "./logos/team_logos/brownseakc.png"
            if os.path.exists(special_path):
                log.info(f"Found league logo via special case: {special_path}")
                return special_path
        
        # Try JSON lookup first
        if league_name in self.league_logos:
            path = self.league_logos[league_name]
            if os.path.exists(path):
                log.info(f"Found league logo from JSON: {path}")
                return path
        
        # Try normalized lookup
        normalized = normalize_name(league_name)
        if normalized in self.league_lookup:
            path = self.league_lookup[normalized]
            if os.path.exists(path):
                log.info(f"Found league logo from normalized lookup: {path}")
                return path
        
        # Try filesystem search
        return find_logo_file(league_name, "league")
    
    def resolve_sponsor_logo(self, sponsor_name: str) -> Optional[str]:
        """Resolve a sponsor logo path"""
        if not sponsor_name:
            return None
        
        # Try JSON lookup first
        if sponsor_name in self.sponsor_logos:
            path = self.sponsor_logos[sponsor_name]
            if os.path.exists(path):
                log.info(f"Found sponsor logo from JSON: {path}")
                return path
        
        # Try normalized lookup
        normalized = normalize_name(sponsor_name)
        if normalized in self.sponsor_lookup:
            path = self.sponsor_lookup[normalized]
            if os.path.exists(path):
                log.info(f"Found sponsor logo from normalized lookup: {path}")
                return path
        
        # Try filesystem search
        return find_logo_file(sponsor_name, "sponsor")
    
    def resolve_any_logo(self, name: str) -> Optional[str]:
        """Try to resolve a logo of any type"""
        # Try team first (most common)
        logo = self.resolve_team_logo(name)
        if logo:
            return logo
        
        # Try league
        logo = self.resolve_league_logo(name)
        if logo:
            return logo
        
        # Try sponsor
        logo = self.resolve_sponsor_logo(name)
        if logo:
            return logo
        
        # Last resort: general search
        return find_logo_file(name, "any")
    
    def batch_resolve_team_logos(self, team_names: list) -> Dict[str, Optional[str]]:
        """Resolve multiple team logos at once"""
        results = {}
        for name in team_names:
            results[name] = self.resolve_team_logo(name)
        return results

# ================= Standalone Functions =================

def resolve_logo(name: str, logo_type: str = "team", 
                json_configs: Dict[str, str] = None) -> Optional[str]:
    """
    Standalone function to resolve a logo
    
    Args:
        name: Name to search for
        logo_type: Type of logo ('team', 'league', 'sponsor', 'any')
        json_configs: Optional dict with paths to JSON config files
    
    Returns:
        Path to logo file or None
    """
    if json_configs:
        resolver = LogoResolver(
            team_logos_file=json_configs.get('team', 'team_logos.json'),
            league_logos_file=json_configs.get('league', 'league_logos.json'),
            sponsor_logos_file=json_configs.get('sponsor', 'sponsor_logos.json')
        )
    else:
        resolver = LogoResolver()
    
    if logo_type == "team":
        return resolver.resolve_team_logo(name)
    elif logo_type == "league":
        return resolver.resolve_league_logo(name)
    elif logo_type == "sponsor":
        return resolver.resolve_sponsor_logo(name)
    else:
        return resolver.resolve_any_logo(name)

# ================= Testing Interface =================

def test_logo_resolution():
    """Test logo resolution with various inputs"""
    print("Testing Logo Resolution")
    print("=" * 50)
    
    resolver = LogoResolver()
    
    test_cases = [
        ("Thunder Hawks", "team"),
        ("Lightning Bolts", "team"),
        ("BrownsEAKC", "league"),
        ("browns", "league"),
        ("ESPN Fantasy", "sponsor"),
        ("Gridiron Gazette", "sponsor"),
    ]
    
    for name, logo_type in test_cases:
        print(f"\nSearching for {logo_type} logo: '{name}'")
        
        if logo_type == "team":
            result = resolver.resolve_team_logo(name)
        elif logo_type == "league":
            result = resolver.resolve_league_logo(name)
        elif logo_type == "sponsor":
            result = resolver.resolve_sponsor_logo(name)
        else:
            result = resolver.resolve_any_logo(name)
        
        if result:
            print(f"  ✅ Found: {result}")
        else:
            print(f"  ❌ Not found")
    
    print("\n" + "=" * 50)
    print("Checking special league logo...")
    
    # Check for the specific brownseakc.png
    special_check = "./logos/team_logos/brownseakc.png"
    if os.path.exists(special_check):
        print(f"✅ brownseakc.png exists at: {special_check}")
    else:
        print(f"❌ brownseakc.png not found at: {special_check}")

def scan_logo_directory():
    """Scan and report all logos found in the system"""
    print("Scanning for all logo files")
    print("=" * 50)
    
    logos_found = {
        'team': [],
        'league': [],
        'sponsor': [],
        'other': []
    }
    
    for directory in DEFAULT_LOGO_DIRS:
        if not os.path.exists(directory):
            continue
        
        print(f"\nScanning {directory}...")
        
        try:
            for filename in os.listdir(directory):
                if any(filename.lower().endswith(ext) for ext in IMAGE_EXTENSIONS):
                    filepath = os.path.join(directory, filename)
                    
                    # Categorize
                    if 'team' in directory.lower():
                        logos_found['team'].append(filepath)
                    elif 'league' in directory.lower():
                        logos_found['league'].append(filepath)
                    elif 'sponsor' in directory.lower():
                        logos_found['sponsor'].append(filepath)
                    else:
                        logos_found['other'].append(filepath)
                    
                    print(f"  Found: {filename}")
        except Exception as e:
            print(f"  Error scanning: {e}")
    
    print("\n" + "=" * 50)
    print("Summary:")
    for category, files in logos_found.items():
        print(f"  {category.capitalize()} logos: {len(files)}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "test":
            test_logo_resolution()
        elif sys.argv[1] == "scan":
            scan_logo_directory()
        elif sys.argv[1] == "find" and len(sys.argv) > 2:
            name = " ".join(sys.argv[2:])
            print(f"Searching for logo: '{name}'")
            
            resolver = LogoResolver()
            result = resolver.resolve_any_logo(name)
            
            if result:
                print(f"✅ Found: {result}")
            else:
                print(f"❌ Not found")
                print("\nTrying filesystem search...")
                result = find_logo_file(name, "any")
                if result:
                    print(f"✅ Found via filesystem: {result}")
                else:
                    print(f"❌ Still not found")
    else:
        print("Logo Resolver Utility")
        print("Usage:")
        print("  python logo_resolver.py test        - Test resolution with sample names")
        print("  python logo_resolver.py scan        - Scan all logo directories")
        print("  python logo_resolver.py find [name] - Find a specific logo")