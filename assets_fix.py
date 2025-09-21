# assets_fix.py
# JSON-driven logo resolver for Gridiron Gazette (teams + league logo)
# - Reads ./team_logos.json (keys = display names, values = filenames OR paths)
# - Handles punctuation/emojis; case/Unicode-insensitive lookups
# - Converts WEBP/GIF/BMP/TIFF -> PNG so python-docx embeds cleanly

from pathlib import Path
import json, re, unicodedata
from functools import lru_cache
from PIL import Image

LOGO_ROOT = Path("./logos/team_logos")
LOGO_MAP_PATH = Path("./team_logos.json")
PLACEHOLDER = LOGO_ROOT / "placeholder.png"  # optional fallback

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
    # Try same stem with any ext if mapped file missing
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

# Public helpers
def find_team_logo(team_name: str) -> Path:
    return find_logo_by_name(team_name)

def find_league_logo(league_display_name: str) -> Path:
    # If you add a JSON key like "LEAGUE:Your League Name": "logos/team_logos/league.png",
    # it’ll be picked up; otherwise we try the display name.
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
