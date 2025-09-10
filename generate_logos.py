#!/usr/bin/env python3
"""
Generate placeholder team logos (PNG) for all teams we know about.

Sources for team names:
  - team_mascots.py  (team_mascots keys)
  - leagues.json via espn_api (optional: --from-espn)

Output:
  - PNG files in logos/generated_logo/
  - team_logos.json mapping { "<Exact Team Name>": "logos/generated_logo/<file>.png" }

Usage:
  python3 generate_logos.py                 # from team_mascots only
  python3 generate_logos.py --from-espn     # also include ESPN league team names
  python3 generate_logos.py --force         # overwrite existing PNGs
"""

from __future__ import annotations
import argparse, json, os, re, hashlib
from pathlib import Path

# ---- optional ESPN support ----
def load_espn_team_names() -> set[str]:
    names: set[str] = set()
    try:
        import json as _json
        from espn_api.football import League
        cfgs = _json.loads(Path("leagues.json").read_text(encoding="utf-8"))
        if not isinstance(cfgs, list):
            cfgs = [cfgs]
        for c in cfgs:
            try:
                L = League(
                    league_id=c["league_id"],
                    year=c["year"],
                    ***REMOVED***
                    ***REMOVED***
                )
                for t in L.teams:
                    names.add(t.team_name)
            except Exception:
                continue
    except Exception:
        pass
    return names

def load_team_mascots() -> dict[str, str]:
    # Prefer importing Python so you keep emojis and casing
    try:
        import team_mascots as TM
        if hasattr(TM, "team_mascots") and isinstance(TM.team_mascots, dict):
            return dict(TM.team_mascots)
    except Exception:
        pass
    # Fallback: team_mascots.json (optional)
    if Path("team_mascots.json").is_file():
        try:
            return json.loads(Path("team_mascots.json").read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

# ---- image generation with Pillow ----
def ensure_pillow():
    try:
        from PIL import Image  # noqa
        return True
    except Exception:
        return False

def color_from_name(name: str) -> tuple[int, int, int]:
    h = hashlib.md5(name.encode("utf-8")).digest()
    r, g, b = h[0], h[1], h[2]
    # keep colors brightish
    return (int(90 + r * 0.6), int(90 + g * 0.6), int(90 + b * 0.6))

def text_color(bg):
    r, g, b = bg
    yiq = (r*299 + g*587 + b*114) / 1000
    return (0, 0, 0) if yiq > 175 else (255, 255, 255)

def initials(name: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", name)
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    s = re.sub(r"[^A-Za-z0-9]", "", name).upper()
    return (s[:2] or "T")

def safe_filename(name: str) -> str:
    # keep a readable, stable filename; emojis/symbols -> underscore
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    return base or "team"

def draw_logo_png(team: str, dest: Path, size=700) -> None:
    from PIL import Image, ImageDraw, ImageFont
    bg = color_from_name(team)
    fg = text_color(bg)

    img = Image.new("RGB", (size, size), color=bg)
    d = ImageDraw.Draw(img)

    # ring / shield
    pad = int(size * 0.06)
    d.ellipse((pad, pad, size - pad, size - pad), outline=fg, width=int(size * 0.035))

    # initials
    text = initials(team)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(size * 0.30))
    except Exception:
        font = ImageFont.load_default()
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - tw) // 2, (size - th) // 2), text, fill=fg, font=font)

    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "PNG")

# ---- main flow ----
def main():
    ap = argparse.ArgumentParser(description="Generate placeholder team logos.")
    ap.add_argument("--from-espn", action="store_true", help="Include team names from leagues.json via espn_api")
    ap.add_argument("--force", action="store_true", help="Overwrite existing images")
    args = ap.parse_args()

    if not ensure_pillow():
        raise SystemExit("Pillow is required. Run: pip install pillow")

    # collect names
    mascots = load_team_mascots()
    names = set(mascots.keys())
    if args.from_espn:
        names |= load_espn_team_names()

    if not names:
        raise SystemExit("No team names found. Add team_mascots.py or use --from-espn with a valid leagues.json.")

    out_dir = Path("logos/generated_logo")
    mapping = {}
    created, skipped = 0, 0

    # existing JSON mapping (will extend/update)
    mapping_path = Path("team_logos.json")
    if mapping_path.is_file():
        try:
            mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        except Exception:
            mapping = {}

    for team in sorted(names):
        fname = safe_filename(team) + ".png"
        dest = out_dir / fname
        if dest.exists() and not args.force:
            mapping[team] = str(dest)
            skipped += 1
            continue
        try:
            draw_logo_png(team, dest)
            mapping[team] = str(dest)
            created += 1
        except Exception as e:
            print(f"[warn] failed to create logo for {team!r}: {e}")

    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Done. Created {created}, skipped {skipped}.")
    print(f"Logos in: {out_dir}")
    print(f"Mapping written to: {mapping_path} (used automatically by mascots_util.py)")

if __name__ == "__main__":
    main()
