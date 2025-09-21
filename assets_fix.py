# assets_fix.py
# Robust team logo resolver for Gridiron Gazette
# - Works with ./logos/team_logos/
# - Handles apostrophes / spaces / case
# - Converts WEBP/GIF to PNG when needed

from pathlib import Path
import re
from PIL import Image

LOGO_ROOT = Path("./logos/team_logos")  # <- matches your repo
PLACEHOLDER = LOGO_ROOT / "placeholder.png"  # optional; add a generic PNG if you want

PREFERRED_EXTS = [".png", ".jpg", ".jpeg"]
ALL_EXTS = PREFERRED_EXTS + [".webp", ".gif", ".bmp", ".tif", ".tiff"]

# explicit overrides if you ever need a one-off mapping
OVERRIDES = {
    # "raw team name lower": "ExactFileName.png"
    "nana's hawks": "Nanas_Hawks.png",  # your case
}

def _sanitize(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s

def _ensure_png(src: Path) -> Path:
    """Convert WEBP/GIF/etc to PNG so python-docx is happy."""
    if src.suffix.lower() in (".png", ".jpg", ".jpeg"):
        return src
    out = src.with_suffix(".png")
    try:
        im = Image.open(src).convert("RGBA")
        out.parent.mkdir(parents=True, exist_ok=True)
        im.save(out, format="PNG")
        return out
    except Exception:
        return src  # fall back; caller will decide placeholder

def find_team_logo(team_name: str) -> Path:
    # 1) explicit override?
    lowered = team_name.lower()
    if lowered in OVERRIDES:
        p = LOGO_ROOT / OVERRIDES[lowered]
        if p.exists():
            return p

    # 2) variant keys to handle possessives & spacing
    key = _sanitize(team_name)                      # e.g., "Nana's Hawks" -> "nana_s_hawks"
    variants = {
        key,
        key.replace("_s_", "s_"),                   # "nanas_hawks"
        key.replace("_s_", "_"),
        key.replace("__", "_"),
        key.rstrip("_"),
    }

    # 3) search preferred formats first
    for base in variants:
        for ext in PREFERRED_EXTS:
            p = LOGO_ROOT / f"{base}{ext}"
            if p.exists():
                return p

    # 4) try any format and convert to PNG if necessary
    for base in variants:
        for ext in ALL_EXTS:
            p = LOGO_ROOT / f"{base}{ext}"
            if p.exists():
                return _ensure_png(p)

    # 5) last resort: placeholder (if present) or just return a path that doesn't crash
    return PLACEHOLDER if PLACEHOLDER.exists() else LOGO_ROOT / "MISSING.png"

def debug_log_logo(team_name: str) -> None:
    p = find_team_logo(team_name)
    note = ""
    if not p.exists():
        note = " (NOT FOUND on disk)"
    elif p.name.lower().endswith((".webp", ".gif", ".bmp", ".tif", ".tiff")):
        note = " (non-preferred format)"
    print(f"[logo] {team_name} -> {p}{note}")
