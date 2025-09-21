# images_attach.py
from pathlib import Path
from docxtpl import InlineImage
from docx.shared import Mm
from assets_fix import find_team_logo, debug_log_logo

# Optional: keys to try if you prefer explicit names.
# If your context uses different keys, add them here or rely on the generic scan below.
TEAM_NAME_KEYS_HINT = {"HOME_TEAM_NAME", "AWAY_TEAM_NAME"}

def _is_image_ext(path: Path) -> bool:
    return path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}

def create_image_objects(doc, context: dict, logo_width_mm: float = 25.0) -> dict:
    """
    Make context safe for docxtpl by converting logo paths/names to InlineImage objects.
    Works with either:
      - *_LOGO_PATH in context (uses as-is if valid), OR
      - *_TEAM_NAME in context (will resolve path via find_team_logo)
    Returns a *new* context (does not mutate the original).
    """
    image_context = dict(context)  # copy

    # 1) If explicit *_LOGO_PATH keys exist, try to use them (but validate!)
    for key, value in list(context.items()):
        if key.endswith("_LOGO_PATH") and value:
            p = Path(str(value))
            logo_key = key.replace("_PATH", "")  # e.g., HOME_LOGO
            try:
                if p.exists() and _is_image_ext(p):
                    image_context[logo_key] = InlineImage(doc, str(p), width=Mm(logo_width_mm))
                    # leave original path in case you need it for logs
                    print(f"[logo] Loaded image for {logo_key}: {p}")
                else:
                    print(f"[logo] Path not usable for {logo_key}: {p} — will try team name fallback if available")
            except Exception as e:
                print(f"[logo] Error loading image {p} for {logo_key}: {e}")

    # 2) Use *_TEAM_NAME keys to resolve logos where needed or missing
    #    This catches Nana's Hawks reliably.
    for key, value in list(context.items()):
        if key.endswith("_TEAM_NAME") and value:
            team_name = str(value)
            # Derive the logo slot name e.g., HOME_LOGO for HOME_TEAM_NAME
            base = key[:-10]  # strip "_TEAM_NAME"
            logo_slot = f"{base}_LOGO"          # what template expects
            # Skip if already filled by *_LOGO_PATH above
            if logo_slot in image_context and isinstance(image_context[logo_slot], InlineImage):
                continue
            try:
                debug_log_logo(team_name)  # log what we pick
                logo_path = find_team_logo(team_name)
                if logo_path and logo_path.exists() and _is_image_ext(logo_path):
                    image_context[logo_slot] = InlineImage(doc, str(logo_path), width=Mm(logo_width_mm))
                    print(f"[logo] Resolved {team_name} -> {logo_path.name} for {logo_slot}")
                else:
                    print(f"[logo] Could not resolve a usable image for {team_name}; leaving {logo_slot} unset or placeholder")
            except Exception as e:
                print(f"[logo] Resolution error for {team_name}: {e}")

    return image_context
