# assets_fix.py
# JSON-driven team logo resolver for Gridiron Gazette
# - Uses ./team_logos.json as source of truth
# - Accepts values like "logos/team_logos/Name.png" or just "Name.png"
# - Handles Unicode/curly quotes/emojis in team names (case-insensitive)
# - Converts WEBP/GIF/etc → PNG for python-docx

from pathlib import Path
import json, re, unicodedata
from functools import lru_cache
from PIL import Image

LOGO_ROOT = Path("./logos/team_logos")
LOGO_MAP_PATH = Path("./team_logos.json")
PLACEHOLDER = LOGO_ROOT / "placeholder.png"    # optional; add if you want a generic fallback

PREFERRED_EXTS = {".png", ".jpg", ".jpeg"}
ALL_EXTS = PREFERRED_EXTS | {".webp", ".gif", ".bmp", ".tif", ".tiff"}

def _norm_key(s: str) -> str:
    # Normalize Unicode (curly quotes/emojis), lower, collapse whitespace
    s = unicodedata.normalize("NFKC", s)
    s = s.strip().lower()
    return s

def _sanitize_filename(name: str) -> str:
    # Best-effort filename from a team name for fallback guessing
    s = unicodedata.normalize("NFKC", name).lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s

def _ensure_png(src: Path) -> Path:
    # Convert WEBP/GIF/etc to PNG so python-docx is happy
    if src.suffix.lower() in PREFERRED_EXTS:
        return src
    out = src.with_suffix(".png")
    try:
        im = Image.open(src).convert("RGBA")
        out.parent.mkdir(parents=True, exist_ok=True)
        im.save(out, format="PNG")
        return out
    except Exception:
        return src  # fall back to original

@lru_cache(maxsize=1)
def _load_map() -> dict:
    if not LOGO_MAP_PATH.exists():
        return {}
    try:
        raw = json.loads(LOGO_MAP_PATH.read_text(encoding="utf-8"))
        # Normalize keys for lookup; keep raw value string
        return { _norm_key(k): v for k, v in raw.items() }
    except Exception as e:
        print(f"[logo] Failed to read {LOGO_MAP_PATH}: {e}")
        return {}

def _value_to_path(value: str) -> Path:
    # Value may be "Nanas_Hawks.png" OR "logos/team_logos/Nanas_Hawks.png"
    p = Path(value)
    if not p.is_absolute() and not str(p).startswith(str(LOGO_ROOT)):
        p = LOGO_ROOT / p
    return p

def find_team_logo(team_name: str) -> Path:
    m = _load_map()
    key = _norm_key(team_name)

    # 1) JSON exact (case/Unicode-insensitive)
    if key in m:
        p = _value_to_path(m[key])
        if p.exists():
            return p
        # try same stem with any ext if mapped file missing
        stem = Path(m[key]).stem
        for ext in ALL_EXTS:
            cand = LOGO_ROOT / f"{stem}{ext}"
            if cand.exists():
                return _ensure_png(cand)

    # 2) Fallback: filename guesses
    base = _sanitize_filename(team_name)
    variants = {
        base,
        base.replace("_s_", "s_"),  # e.g., "nana_s_hawks" -> "nanas_hawks"
        base.replace("_s_", "_"),
        base.replace("__", "_"),
        base.rstrip("_"),
    }
    # preferred formats first
    for v in variants:
        for ext in PREFERRED_EXTS:
            p = LOGO_ROOT / f"{v}{ext}"
            if p.exists():
                return p
    # any format (convert if needed)
    for v in variants:
        for ext in ALL_EXTS:
            p = LOGO_ROOT / f"{v}{ext}"
            if p.exists():
                return _ensure_png(p)

    return PLACEHOLDER if PLACEHOLDER.exists() else LOGO_ROOT / "MISSING.png"

def debug_log_logo(team_name: str) -> None:
    p = find_team_logo(team_name)
    note = ""
    if not p.exists():
        note = " (NOT FOUND)"
    elif p.suffix.lower() not in PREFERRED_EXTS:
        note = f" (non-preferred: {p.suffix})"
    print(f"[logo] {team_name} -> {p}{note}")

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
