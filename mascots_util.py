# mascots_util.py
# Source of truth for team mascots and logos.
# - Pulls mascot text from your existing team_mascots.py (team_mascots dict).
# - Optionally pulls explicit logo paths from team_mascots.py (team_logos dict).
# - If no explicit path, it searches common folders like assets/logos/ or logos/.

from __future__ import annotations
import os, re, unicodedata
from typing import Optional

# --- load user-provided data ---
try:
    from team_mascots import team_mascots as MASCOTS_RAW  # REQUIRED by you
except Exception:
    MASCOTS_RAW = {}

# Optional dict you can define in team_mascots.py:
# team_logos = {"Wafflers": "assets/logos/wafflers.png", ...}
try:
    from team_mascots import team_logos as LOGOS_RAW  # OPTIONAL
except Exception:
    LOGOS_RAW = {}

# --- normalization helpers ---
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", (s or "")).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def _alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _norm(s))

# build indices for mascots
_MASCOTS_BY_NORM = {}
_MASCOTS_BY_ALNUM = {}
for k, v in MASCOTS_RAW.items():
    nk = _norm(k)
    _MASCOTS_BY_NORM[nk] = v
    _MASCOTS_BY_ALNUM[_alnum(k)] = v

# build indices for explicit logo paths (optional)
_LOGOS_BY_NORM = {}
_LOGOS_BY_ALNUM = {}
for k, v in LOGOS_RAW.items():
    nk = _norm(k)
    _LOGOS_BY_NORM[nk] = v
    _LOGOS_BY_ALNUM[_alnum(k)] = v

def mascot_for(team_name: str) -> Optional[str]:
    if not team_name:
        return None
    nk = _norm(team_name)
    hit = _MASCOTS_BY_NORM.get(nk)
    if hit:
        return hit
    return _MASCOTS_BY_ALNUM.get(_alnum(team_name))

# --- logo lookup ---
_CANDIDATE_DIRS = ["assets/logos", "assets/Logos", "logos", "static/logos", "images/logos"]

def _search_logo_files(team_name: str) -> Optional[str]:
    """Try to find a logo file by normalized filename in common folders."""
    if not team_name:
        return None
    stem_candidates = {
        _alnum(team_name),  # "thewafflers"
        re.sub(r"[^a-z0-9]+", "-", _norm(team_name)).strip("-"),  # "the-wafflers"
        _norm(team_name).replace(" ", "_"),  # "the_wafflers"
    }
    exts = [".png", ".jpg", ".jpeg", ".gif"]  # (python-docx doesn't support svg)
    for d in _CANDIDATE_DIRS:
        if not os.path.isdir(d):
            continue
        try:
            names = os.listdir(d)
        except Exception:
            continue
        low = {n.lower(): n for n in names}  # keep original case for returned path
        for stem in stem_candidates:
            for ext in exts:
                guess = f"{stem}{ext}"
                if guess in low:
                    return os.path.join(d, low[guess])
    return None

def logo_for(team_name: str) -> Optional[str]:
    """Return a filesystem path to the team's logo if found."""
    if not team_name:
        return None
    # explicit mapping first
    path = _LOGOS_BY_NORM.get(_norm(team_name)) or _LOGOS_BY_ALNUM.get(_alnum(team_name))
    if path and os.path.isfile(path):
        return path
    # try auto-discovery
    path = _search_logo_files(team_name)
    if path and os.path.isfile(path):
        return path
    return None
