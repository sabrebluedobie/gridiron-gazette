# assets_fix.py
# JSON-driven logo resolver for Gridiron Gazette (teams + league logo)
# - Uses ./team_logos.json as source of truth
# - Accepts values as filenames (e.g., "Phoenix_Blues.png") or paths (e.g., "logos/team_logos/Phoenix_Blues.png")
# - Handles punctuation/emojis; case/Unicode-insensitive keys
# - Converts WEBP/GIF/etc. to PNG so python-docx can embed cleanly

from pathlib import Path
import json, re, unicodedata
from functools import lru_cache
from PIL import Image

LOGO_ROOT = Path("./logos/team_logos")
LOGO_MAP_PATH = Path("./team_logos.json")
PLACEHOLDER = LOGO_ROOT / "placeholder.png"     # optional fallback asset

PREFERRED = {".png", ".jpg", ".jpeg"}
ALL_EXTS  = PREFERRED | {".webp", ".gif", ".bmp", ".tif", ".tiff"}

def _norm_key(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    return s.strip().lower()

def _sanitize(name: str) -> str:
    s = unicodedata.normalize("NFKC", name or "").lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s

def _ensure_png(src: Path) -> Path:
    if src.suffix.lower() in PREFERRED:
        return src
    out = src.with_suffix(".png")
    try:
        im = Image.open(src).convert("RGBA")
        out.parent.mkdir(parents=True, exist_ok=True)
        im.save(out, format="PNG")
        return out
    except Exception:
        return src  # fall back

@lru_cache(maxsize=1)
def _load_map() -> dict:
    if not LOGO_MAP_PATH.exists():
        return {}
    try:
        raw = json.loads(LOGO_MAP_PATH.read_text(encoding="utf-8"))
        # normalize keys for robust lookups
        return { _norm_key(k): v for k, v in raw.items() }
    except Exception as e:
        print(f"[logo] Failed to read {LOGO_MAP_PATH}: {e}")
        return {}

def _value_to_path(value: str) -> Path:
    p = Path(value)
    # If it's not absolute and not already under LOGO_ROOT, treat as basename under LOGO_ROOT
    if not p.is_absolute() and not str(p).startswith(str(LOGO_ROOT)):
        p = LOGO_ROOT / p
    return p

def _resolve_from_map(display_name: str) -> Path | None:
    m = _load_map()
    key = _norm_key(display_name)
    val = m.get(key)
    if not val:
        return None
    p = _value_to_path(val)
    if p.exists():
        return p
    # Try same stem with any extension if mapped file missing
    stem = Path(val).stem
    for ext in ALL_EXTS:
        cand = LOGO_ROOT / f"{stem}{ext}"
        if cand.exists():
            return _ensure_png(cand)
    return None

def _resolve_by_guessing(display_name: str) -> Path | None:
    base = _sanitize(display_name)
    variants = {
        base,
        base.replace("_s_", "s_"),  # "nana_s_hawks" -> "nanas_hawks"
        base.replace("_s_", "_"),
        base.replace("__", "_"),
        base.rstrip("_"),
    }
    for v in variants:
        for ext in PREFERRED:
            p = LOGO_ROOT / f"{v}{ext}"
            if p.exists():
                return p
    for v in variants:
        for ext in ALL_EXTS:
            p = LOGO_ROOT / f"{v}{ext}"
            if p.exists():
                return _ensure_png(p)
    return None

def find_logo_by_name(display_name: str) -> Path:
    # 1) JSON map
    p = _resolve_from_map(display_name)
    if p:
        return p
    # 2) Guessing
    p = _resolve_by_guessing(display_name)
    if p:
        return p
    # 3) Fallback
    return PLACEHOLDER if PLACEHOLDER.exists() else LOGO_ROOT / "MISSING.png"

# Convenience aliases
def find_team_logo(team_name: str) -> Path:
    return find_logo_by_name(team_name)

def find_league_logo(league_display_name: str) -> Path:
    # Try explicit league key in JSON first, else fall back to display name guessing.
    # You can add a JSON entry like:  "LEAGUE:Browns SEA/KC": "logos/team_logos/League_Browns_SEA_KC.png"
    m = _load_map()
    special = m.get(_norm_key(f"LEAGUE:{league_display_name}"))
    if special:
        p = _value_to_path(special)
        if p.exists():
            return p
    return find_logo_by_name(league_display_name)

def debug_log_logo(name: str, kind="team"):
    p = find_logo_by_name(name)
    note = ""
    if not p.exists():
        note = " (NOT FOUND)"
    elif p.suffix.lower() not in PREFERRED:
        note = f" (non-preferred: {p.suffix})"
    print(f"[logo:{kind}] {name} -> {p}{note}")

def validate_logo_map() -> int:
    """Return count of missing files referenced by team_logos.json"""
    missing = 0
    m = _load_map()
    for k, v in m.items():
        p = _value_to_path(v)
        if not p.exists():
            print(f"[logo:missing] {k} -> {v}")
            missing += 1
    return missing
