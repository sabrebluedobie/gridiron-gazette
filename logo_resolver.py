#!/usr/bin/env python3
"""
logo_resolver.py — local-first logo lookup with league-aware overrides.

Priority:
  1) TEAM_LOGOS_FILE (or team_logos.json) explicit overrides  ← source of truth
  2) Local filename match under ./logos/team_logos/ (smart matching)
  3) No network calls; fully offline & stable.

Supports:
- Flat JSON: { "Team A": "logos/team_logos/a.png", "LEAGUE_LOGO": "..." }
- Nested JSON: { "leagues": { "887998": {...}, "Browns SEA/KC": {...} }, ... }
  Selected by LEAGUE_ID or LEAGUE_DISPLAY_NAME.
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional, List
import json, re, os

TEAM_DIR = Path("logos/team_logos")
SPECIAL_DIR = Path("logos/special")
EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def _norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[\W_]+", " ", s, flags=re.UNICODE)  # strip emoji/punct/underscores
    return " ".join(s.split())


def _read_json(path: Path) -> Dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _load_overrides() -> Dict[str, str]:
    """
    Load overrides from:
      1) TEAM_LOGOS_FILE env (e.g., team-logos.json)
      2) team_logos.json (repo root)

    Merge order:
      - flat (top-level) keys first
      - then league-specific nested block, which overrides flat
    """
    fname = os.getenv("TEAM_LOGOS_FILE") or "team_logos.json"
    p = Path(fname)
    if not p.exists() and fname != "team_logos.json":
        p = Path("team_logos.json")

    data = _read_json(p)
    if not isinstance(data, dict):
        return {}

    # flat entries
    flat: Dict[str, str] = {k: v for k, v in data.items()
                            if isinstance(k, str) and isinstance(v, str) and v}

    # nested leagues block
    leagues = data.get("leagues")
    if isinstance(leagues, dict):
        lid = os.getenv("LEAGUE_ID")
        lname = os.getenv("LEAGUE_DISPLAY_NAME")
        for key in (lid, lname):
            if key and isinstance(leagues.get(key), dict):
                nested = {k: v for k, v in leagues[key].items()
                          if isinstance(k, str) and isinstance(v, str) and v}
                flat.update(nested)  # nested wins
                break

    return flat


_OVERRIDES = _load_overrides()


def _find_local_logo(team_name: str) -> Optional[Path]:
    """Search ./logos/team_logos for best filename match."""
    if not TEAM_DIR.exists():
        return None
    want = team_name.strip()
    want_norm = _norm(want)

    candidates: List[Path] = [p for p in TEAM_DIR.rglob("*")
                              if p.is_file() and p.suffix.lower() in EXTS]
    if not candidates:
        return None

    # 1) exact base name (case-insensitive)
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
    # 4) word overlap
    want_words = set(want_norm.split())
    need = max(1, len(want_words) // 2)
    for p in candidates:
        words = set(_norm(p.stem).split())
        if len(want_words & words) >= need:
            return p

    return None


def team_logo(team_name: str) -> Optional[str]:
    """Return filesystem path to best team logo (overrides win)."""
    if team_name in _OVERRIDES and _OVERRIDES[team_name]:
        return _OVERRIDES[team_name]
    p = _find_local_logo(team_name)
    return str(p) if p else None


def league_logo(league_display_name: str) -> Optional[str]:
    """Resolve league logo: override → ./logos/special/league.* → team-style match."""
    if _OVERRIDES.get("LEAGUE_LOGO"):
        return _OVERRIDES["LEAGUE_LOGO"]
    for ext in EXTS:
        p = SPECIAL_DIR / f"league{ext}"
        if p.exists():
            return str(p)
    p = _find_local_logo(league_display_name)
    return str(p) if p else None


def sponsor_logo(default_name: str = "Gridiron Gazette") -> Optional[str]:
    """Resolve sponsor logo: override → ./logos/special/sponsor.* → fallback name match."""
    if _OVERRIDES.get("SPONSOR_LOGO"):
        return _OVERRIDES["SPONSOR_LOGO"]
    for ext in EXTS:
        p = SPECIAL_DIR / f"sponsor{ext}"
        if p.exists():
            return str(p)
    p = _find_local_logo(default_name)
    return str(p) if p else None
