from __future__ import annotations
import json
import os
import re
from pathlib import Path
from typing import Dict, Optional

# --- Config / locations ---
TEAM_LOGOS_FILE = os.getenv("TEAM_LOGOS_FILE", "team_logos.json")
LEAGUE_LOGOS_FILE = os.getenv("LEAGUE_LOGOS_FILE", "league_logos.json")
SPONSOR_LOGOS_FILE = os.getenv("SPONSOR_LOGOS_FILE", "sponsor_logos.json")

LOGO_DIRS = [
    Path("logos/team_logos"),
    Path("logos/generated_logos"),
    Path("logos"),
]

DEFAULT_TEAM_LOGO   = Path("logos/_default.png")
DEFAULT_LEAGUE_DIR  = Path("logos/league_logos")
DEFAULT_SPONSOR_DIR = Path("logos/sponsor_logos")

def _load_json(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}

def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s

# ------------- Team logos (mapping + filesystem) -------------
_JSON_TEAM_MAP: Optional[Dict[str, str]] = None
_FILE_CACHE: Dict[str, Optional[Path]] = {}

def _build_team_map() -> Dict[str, str]:
    data = _load_json(Path(TEAM_LOGOS_FILE))
    result: Dict[str, str] = {}
    if not data:
        return result

    # Flat map: { "Team Name": "path.png" }
    if all(isinstance(v, str) for v in data.values()):
        for k, v in data.items():
            result[_norm(k)] = v
        return result

    # Hierarchical: { "default": {...}, "leagues": { "887998": {...}, "Browns SEA/KC": {...}}}
    league_id = os.getenv("LEAGUE_ID") or ""
    league_name = os.getenv("LEAGUE_DISPLAY_NAME") or ""

    default_map = data.get("default") or {}
    for k, v in default_map.items():
        result[_norm(k)] = v

    leagues = data.get("leagues") or {}
    if isinstance(leagues, dict):
        if league_id and league_id in leagues:
            for k, v in (leagues[league_id] or {}).items():
                result[_norm(k)] = v
        if league_name and league_name in leagues:
            for k, v in (leagues[league_name] or {}).items():
                result[_norm(k)] = v

    return result

def _json_team_map() -> Dict[str, str]:
    global _JSON_TEAM_MAP
    if _JSON_TEAM_MAP is None:
        _JSON_TEAM_MAP = _build_team_map()
    return _JSON_TEAM_MAP

def _find_in_dirs(norm_name: str) -> Optional[Path]:
    if norm_name in _FILE_CACHE:
        return _FILE_CACHE[norm_name]

    exts = [".png", ".jpg", ".jpeg", ".gif", ".webp"]
    # exact filename
    for d in LOGO_DIRS:
        for ext in exts:
            p = d / f"{norm_name}{ext}"
            if p.exists():
                _FILE_CACHE[norm_name] = p
                return p

    # loose contains match
    candidates = []
    for d in LOGO_DIRS:
        if not d.exists():
            continue
        for p in d.iterdir():
            if p.is_file():
                stem = _norm(p.stem)
                if norm_name in stem or stem in norm_name:
                    candidates.append(p)
    if candidates:
        _FILE_CACHE[norm_name] = candidates[0]
        return candidates[0]

    _FILE_CACHE[norm_name] = None
    return None

def team_logo(team_name: str) -> Optional[str]:
    norm = _norm(team_name)
    if not norm:
        return str(DEFAULT_TEAM_LOGO) if DEFAULT_TEAM_LOGO.exists() else None

    # 1) JSON mapping (as in commit 8df2db8 where filenames were lowercased)
    jmap = _json_team_map()
    if norm in jmap:
        p = Path(jmap[norm])
        if p.exists():
            return str(p)

    # 2) Filesystem search
    p = _find_in_dirs(norm)
    if p and p.exists():
        return str(p)

    # 3) default
    return str(DEFAULT_TEAM_LOGO) if DEFAULT_TEAM_LOGO.exists() else None

# ------------- League/Sponsor logos (JSON + default dirs) -------------

def _find_brand_logo(display_name: str, json_file: str, default_dir: Path) -> Optional[str]:
    """
    Generic lookup used by league_logo/sponsor_logo to mimic gazette_helpers.find_* from 8df2db8.
    Priority:
      1) exact key in JSON -> path exists
      2) slug-match key in JSON -> path exists
      3) scan default_dir for a slugged filename (e.g., BrownSeaKC -> brownseakc.png)
      4) None if not found
    """
    nm = display_name or ""
    slug = _norm(nm)
    mapping = _load_json(Path(json_file))

    # 1) direct key
    rel = mapping.get(nm)
    if isinstance(rel, str) and Path(rel).exists():
        return str(Path(rel))

    # 2) slug-match key
    for k, v in mapping.items():
        if _norm(k) == slug and isinstance(v, str) and Path(v).exists():
            return str(Path(v))

    # 3) scan folder by slug
    if default_dir.exists():
        for p in default_dir.glob("*.*"):
            if _norm(p.stem) == slug and p.is_file():
                return str(p)

    return None

def league_logo(name: Optional[str] = None) -> Optional[str]:
    # prefer explicit arg, then env/cfg
    league_name = name or os.getenv("LEAGUE_DISPLAY_NAME") or os.getenv("LEAGUE_NAME") or ""
    # Support the 8df2db8 behavior: league_logos.json + logos/league_logos/
    return _find_brand_logo(league_name, LEAGUE_LOGOS_FILE, DEFAULT_LEAGUE_DIR)

def sponsor_logo(name: Optional[str] = None) -> Optional[str]:
    sponsor_name = name or os.getenv("SPONSOR_NAME") or "Gridiron Gazette"
    # Support the 8df2db8 behavior: sponsor_logos.json + logos/sponsor_logos/
    return _find_brand_logo(sponsor_name, SPONSOR_LOGOS_FILE, DEFAULT_SPONSOR_DIR)
