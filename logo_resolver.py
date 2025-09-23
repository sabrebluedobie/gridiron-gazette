#!/usr/bin/env python3
"""
logo_resolver.py — local-first logo lookup with smart matching

Priority:
  1) team_logos.json explicit override (exact team name or special keys)
  2) Local folder match in ./logos/team_logos/ (normalized fuzzy match)
  3) (No network calls — fully offline & stable)

Special logos (optional):
  - LEAGUE_LOGO  -> ./logos/special/league.(png|jpg|jpeg|gif|webp)
  - SPONSOR_LOGO -> ./logos/special/sponsor.(png|jpg|jpeg|gif|webp)

Usage:
  from logo_resolver import team_logo, league_logo, sponsor_logo
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional, List
import json, re

TEAM_DIR = Path("logos/team_logos")
SPECIAL_DIR = Path("logos/special")
EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def _norm(s: str) -> str:
    s = s.lower()
    # remove punctuation / emoji / underscores -> spaces
    s = re.sub(r"[\W_]+", " ", s, flags=re.UNICODE)
    s = " ".join(s.split())
    return s


def _load_overrides() -> Dict[str, str]:
    p = Path("team_logos.json")
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        out = {}
        for k, v in data.items():
            if isinstance(v, str) and v:
                out[str(k)] = v
        return out
    except Exception:
        return {}


_OVERRIDES = _load_overrides()


def _find_local_logo(team_name: str) -> Optional[Path]:
    """
    Search ./logos/team_logos for the best match to team_name.
    Match order:
      - exact filename (case-insensitive, any ext)
      - normalized exact match (spaces/punct stripped)
      - startswith / contains (normalized)
      - word overlap heuristic
    """
    if not TEAM_DIR.exists():
        return None

    want = team_name.strip()
    want_norm = _norm(want)

    candidates: List[Path] = [
        p for p in TEAM_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in EXTS
    ]
    if not candidates:
        return None

    # 1) exact base name
    for p in candidates:
        if p.stem.lower() == want.lower():
            return p

    # 2) normalized exact
    for p in candidates:
        if _norm(p.stem) == want_norm:
            return p

    # 3) startswith / contains (normalized)
    for p in candidates:
        stem = _norm(p.stem)
        if stem.startswith(want_norm) or want_norm.startswith(stem):
            return p
    for p in candidates:
        stem = _norm(p.stem)
        if want_norm in stem or stem in want_norm:
            return p

    # 4) word overlap (>= half the words match, at least 1)
    want_words = set(want_norm.split())
    need = max(1, len(want_words) // 2)
    for p in candidates:
        words = set(_norm(p.stem).split())
        if len(want_words & words) >= need:
            return p

    return None


def team_logo(team_name: str) -> Optional[str]:
    """Return filesystem path to the best local team logo, or None."""
    # explicit override wins
    if team_name in _OVERRIDES and _OVERRIDES[team_name]:
        return _OVERRIDES[team_name]
    p = _find_local_logo(team_name)
    return str(p) if p else None


def league_logo(league_display_name: str) -> Optional[str]:
    """Resolve league logo via override, then ./logos/special/league.* then team-style match."""
    if _OVERRIDES.get("LEAGUE_LOGO"):
        return _OVERRIDES["LEAGUE_LOGO"]

    for ext in EXTS:
        p = SPECIAL_DIR / f"league{ext}"
        if p.exists():
            return str(p)

    p = _find_local_logo(league_display_name)
    return str(p) if p else None


def sponsor_logo(default_name: str = "Gridiron Gazette") -> Optional[str]:
    """Resolve sponsor logo via override, then ./logos/special/sponsor.* then fallback team-style match."""
    if _OVERRIDES.get("SPONSOR_LOGO"):
        return _OVERRIDES["SPONSOR_LOGO"]

    for ext in EXTS:
        p = SPECIAL_DIR / f"sponsor{ext}"
        if p.exists():
            return str(p)

    p = _find_local_logo(default_name)
    return str(p) if p else None
