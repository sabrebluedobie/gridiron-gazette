#!/usr/bin/env python3
"""
logo_resolver.py — robust logo lookup with fuzzy matching & JSON mappings
"""

import json
import re
import unicodedata
from pathlib import Path
from functools import lru_cache
from typing import Optional, Dict

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
    s = unicodedata.normalize("NFKC", s).strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _safe_name(s: str) -> str:
    s = _norm(s).replace(" ", "_")
    return re.sub(r"[^\w-]", "", s)


@lru_cache(maxsize=3)
def _load_map(p: Path) -> Dict[str, str]:
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return {_norm(k): v for k, v in raw.items()}
    except Exception:
        return {}


def _find(name: str, logo_dir: Path, mapping: Dict[str, str], default_name: str = "_default.png") -> Optional[str]:
    logo_dir.mkdir(parents=True, exist_ok=True)
    norm = _norm(name)

    # 1) mapping lookup
    if name in mapping:
        path = BASE_DIR / mapping[name]
        if path.exists(): return str(path)
    if norm in mapping:
        path = BASE_DIR / mapping[norm]
        if path.exists(): return str(path)

    # 2) filename search
    safe = _safe_name(name)
    variants = [safe, safe.replace("_s_", "s_"), safe.replace("_", "")]
    for v in variants:
        for ext in PREFERRED_EXTS:
            path = logo_dir / f"{v}{ext}"
            if path.exists(): return str(path)
    for v in variants:
        for ext in ALL_EXTS:
            path = logo_dir / f"{v}{ext}"
            if path.exists(): return str(path)

    # 3) fuzzy contains
    for f in logo_dir.glob("*"):
        if f.suffix.lower() not in ALL_EXTS: continue
        if norm in _norm(f.stem) or _norm(f.stem) in norm:
            return str(f)

    # 4) default
    d = logo_dir / default_name
    if d.exists(): return str(d)
    return None


def team_logo(name: str) -> Optional[str]:
    return _find(name, TEAM_LOGOS_DIR, _load_map(TEAM_LOGOS_JSON), "_default.png")


def league_logo(name: str) -> Optional[str]:
    return _find(name, LEAGUE_LOGOS_DIR, _load_map(LEAGUE_LOGOS_JSON), "_default.png")


def sponsor_logo(name: str) -> Optional[str]:
    return _find(name, SPONSOR_LOGOS_DIR, _load_map(SPONSOR_LOGOS_JSON), "_default.png")
