# mascots_util.py
# Robust mascot + logo lookup with recursive search and helpful debug.

from __future__ import annotations
import os, re, unicodedata, json
from typing import Optional
from pathlib import Path

# ---------- normalization ----------
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", (s or "")).strip().lower()
    return re.sub(r"\s+", " ", s)

def _alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _norm(s))

# ---------- load mascots (Python dict or JSON fallback) ----------
MASCOTS_RAW = {}
LOGOS_RAW = {}

# Prefer Python file in repo root
try:
    import team_mascots  # your file: team_mascots.py
    if hasattr(team_mascots, "team_mascots"):
        MASCOTS_RAW = dict(team_mascots.team_mascots)
    if hasattr(team_mascots, "team_logos"):
        LOGOS_RAW = dict(team_mascots.team_logos)
except Exception:
    pass

# Optional JSON fallback if Python import fails
if not MASCOTS_RAW and Path("team_mascots.json").is_file():
    try:
        MASCOTS_RAW = json.loads(Path("team_mascots.json").read_text(encoding="utf-8"))
    except Exception:
        MASCOTS_RAW = {}

# ---------- build mascot indices ----------
_MASCOTS_BY_NORM: dict[str,str] = {}
_MASCOTS_BY_ALNUM: dict[str,str] = {}
for k, v in (MASCOTS_RAW or {}).items():
    nk = _norm(k)
    _MASCOTS_BY_NORM[nk] = v
    _MASCOTS_BY_ALNUM[_alnum(k)] = v

# ---------- logo config (search from repo root) ----------
# Resolve from this file’s directory to be stable no matter the CWD.
_REPO_ROOT = Path(__file__).resolve().parent

# Add your folders here; search is recursive.
_CANDIDATE_DIRS = [
    _REPO_ROOT / "assets" / "logos",
    _REPO_ROOT / "assets" / "Logos",
    _REPO_ROOT / "logos",
    _REPO_ROOT / "logos" / "generated_logo",   # <= your note
    _REPO_ROOT / "static" / "logos",
    _REPO_ROOT / "images" / "logos",
]

# Build logo index (normalized filename keys -> absolute file path)
def _iter_logo_files():
    exts = (".png", ".jpg", ".jpeg", ".gif")
    for base in _CANDIDATE_DIRS:
        if not base.is_dir(): 
            continue
        for dirpath, _, filenames in os.walk(base):
            for n in filenames:
                if n.lower().endswith(exts):
                    yield Path(dirpath) / n

_LOGO_INDEX: dict[str, str] = {}
def _rebuild_logo_index():
    _LOGO_INDEX.clear()
    # explicit mappings first
    for team, path in (LOGOS_RAW or {}).items():
        p = Path(path)
        if not p.is_absolute():
            p = _REPO_ROOT / path
        if p.is_file():
            _LOGO_INDEX[_alnum(team)] = str(p)
    # discovered files
    for path in _iter_logo_files():
        base = path.stem
        for key in {
            _alnum(base),
            re.sub(r"[^a-z0-9]+", "-", _norm(base)).strip("-"),
            _norm(base).replace(" ", "_"),
        }:
            _LOGO_INDEX.setdefault(key, str(path))

_rebuild_logo_index()

# ---------- public API ----------
def mascot_for(team_name: str) -> Optional[str]:
    if not team_name:
        return None
    nk = _norm(team_name)
    return _MASCOTS_BY_NORM.get(nk) or _MASCOTS_BY_ALNUM.get(_alnum(team_name))

def logo_for(team_name: str) -> Optional[str]:
    if not team_name:
        return None
    # explicit mapping first
    p = LOGOS_RAW.get(team_name) or LOGOS_RAW.get(_norm(team_name)) or LOGOS_RAW.get(_alnum(team_name))
    if p:
        pth = Path(p)
        if not pth.is_absolute():
            pth = _REPO_ROOT / p
        return str(pth) if pth.is_file() else None
    # index match
    for key in {
        _alnum(team_name),
        re.sub(r"[^a-z0-9]+", "-", _norm(team_name)).strip("-"),
        _norm(team_name).replace(" ", "_"),
    }:
        if key in _LOGO_INDEX:
            return _LOGO_INDEX[key]
    return None

# Optional: quick introspection helpers
def debug_info(team_name: str) -> dict:
    return {
        "team_name": team_name,
        "norm": _norm(team_name),
        "alnum": _alnum(team_name),
        "mascot_found": mascot_for(team_name),
        "logo_found": logo_for(team_name),
        "logo_dirs": [str(d) for d in _CANDIDATE_DIRS],
        "logo_index_size": len(_LOGO_INDEX),
        "repo_root": str(_REPO_ROOT),
        "mascot_keys_sample": list((MASCOTS_RAW or {}).keys())[:10],
    }
