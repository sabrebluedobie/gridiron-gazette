#!/usr/bin/env python3
"""
Description-aware local logo generator (no API).
- Uses team_mascots.py descriptions to guide colors + emblem.
- Writes transparent PNGs to logos/ai/ and updates team_logos.json.

Usage:
  python3 generate_logos.py
  python3 generate_logos.py --from-espn   # include ESPN team_name set
  python3 generate_logos.py --force       # overwrite existing images
"""

from __future__ import annotations
import argparse, json, os, re, hashlib, math
from pathlib import Path

# ---- load sources ----
def load_team_mascots() -> dict[str, str]:
    try:
        import team_mascots as TM
        if hasattr(TM, "team_mascots") and isinstance(TM.team_mascots, dict):
            return dict(TM.team_mascots)
    except Exception:
        pass
    p = Path("team_mascots.json")
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def load_espn_team_names() -> set[str]:
    names: set[str] = set()
    try:
        from espn_api.football import League
        cfgs = json.loads(Path("leagues.json").read_text(encoding="utf-8"))
        if not isinstance(cfgs, list):
            cfgs = [cfgs]
        for c in cfgs:
            try:
                L = League(league_id=c["league_id"], year=c["year"],
                           ***REMOVED***
                for t in L.teams:
                    names.add(t.team_name)
            except Exception:
                continue
    except Exception:
        pass
    return names

# ---- pillow helpers ----
def ensure_pillow():
    try:
        from PIL import Image  # noqa
        return True
    except Exception:
        return False

# ---- styling from description ----
def initials(name: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", name)
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    s = re.sub(r"[^A-Za-z0-9]", "", name).upper()
    return (s[:2] or "T")

def hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def base_color_from_name(name: str):
    """Deterministic bright-ish base color from team name."""
    h = hashlib.md5(name.encode("utf-8")).hexdigest()
    r = 90 + int(int(h[0:2], 16) * 0.6)
    g = 90 + int(int(h[2:4], 16) * 0.6)
    b = 90 + int(int(h[4:6], 16) * 0.6)
    return (r, g, b)

def theme_from_desc(name: str, desc: str | None):
    """
    Pick palette + emblem keyword from the description, fallback to name hash.
    Emblems: bolt | crown | hammer | star | wing | claw | flame | shield-only
    """
    d = (desc or "").lower()

    # palette hints
    if any(k in d for k in ["storm", "lightning", "thunder", "cloud"]):
        base = hex_to_rgb("#2F5DAD")  # deep blue
        accent = hex_to_rgb("#F2D544")  # lightning yellow
        emblem = "bolt"
    elif any(k in d for k in ["fire", "flame", "heat", "inferno"]):
        base = hex_to_rgb("#C63C22")  # red-orange
        accent = hex_to_rgb("#F8B133")
        emblem = "flame"
    elif any(k in d for k in ["hawk", "eagle", "owl", "bird", "falcon"]):
        base = hex_to_rgb("#2C5F2D")  # green
        accent = hex_to_rgb("#E0C872")
        emblem = "wing"
    elif any(k in d for k in ["puma", "panther", "tiger", "lion", "cat", "cougar"]):
        base = hex_to_rgb("#1E1E24")  # near black
        accent = hex_to_rgb("#D4AF37")  # gold
        emblem = "claw"
    elif any(k in d for k in ["rebel", "skull", "bones"]):
        base = hex_to_rgb("#232323")
        accent = hex_to_rgb("#E63946")
        emblem = "star"
    elif any(k in d for k in ["weld", "forge", "steel", "hammer", "smith"]):
        base = hex_to_rgb("#37474F")  # steel gray
        accent = hex_to_rgb("#B0BEC5")
        emblem = "hammer"
    elif any(k in d for k in ["king", "queen", "champ", "royal", "crown"]):
        base = hex_to_rgb("#00205B")  # royal blue
        accent = hex_to_rgb("#D4AF37")  # gold
        emblem = "crown"
    else:
        base = base_color_from_name(name)
        accent = (255 - base[0]//2, 255 - base[1]//2, 255 - base[2]//2)
        emblem = "shield"  # simple badge w/ initials

    return base, accent, emblem

def readable_fg(bg):
    r, g, b = bg
    yiq = (r*299 + g*587 + b*114) / 1000
    return (0, 0, 0) if yiq > 170 else (255, 255, 255)

# ---- drawing primitives ----
def draw_logo(team: str, desc: str | None, dest: Path, size=900):
    from PIL import Image, ImageDraw, ImageFont

    base, accent, emblem = theme_from_desc(team, desc)
    bg = (0, 0, 0, 0)  # transparent
    img = Image.new("RGBA", (size, size), bg)
    d = ImageDraw.Draw(img)

    cx, cy = size//2, size//2
    pad = int(size * 0.06)

    # badge circle
    ring_w = int(size * 0.04)
    d.ellipse((pad, pad, size-pad, size-pad), fill=base+(255,), outline=readable_fg(base)+(255,), width=ring_w)

    # inner field
    pad2 = pad + ring_w + int(size*0.015)
    d.ellipse((pad2, pad2, size-pad2, size-pad2), fill=(0,0,0,0), outline=None)

    # emblem in center
    em_box = (int(size*0.22), int(size*0.22), int(size*0.78), int(size*0.78))
    if emblem == "bolt":
        draw_bolt(d, em_box, fill=accent+(255,))
    elif emblem == "flame":
        draw_flame(d, em_box, fill=accent+(255,))
    elif emblem == "wing":
        draw_wing(d, em_box, fill=accent+(220,))
    elif emblem == "claw":
        draw_claw(d, em_box, fill=accent+(230,))
    elif emblem == "hammer":
        draw_hammer(d, em_box, fill=accent+(255,))
    elif emblem == "crown":
        draw_crown(d, em_box, fill=accent+(255,))
    elif emblem == "star":
        draw_star(d, em_box, fill=accent+(255,))
    else:
        # shield chevron
        draw_shield_chevron(d, em_box, fill=accent+(200,))

    # initials
    text = initials(team)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(size * 0.22))
    except Exception:
        font = ImageFont.load_default()
    bbox = d.textbbox((0,0), text, font=font)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    d.text((cx - tw//2, cy - th//2), text, fill=readable_fg(base)+(255,), font=font)

    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "PNG")

def draw_star(d, box, fill):
    x0,y0,x1,y1 = box
    cx = (x0+x1)/2; cy=(y0+y1)/2; r=(x1-x0)/2
    pts=[]
    for i in range(10):
        angle = -math.pi/2 + i*math.pi/5
        rr = r if i%2==0 else r*0.45
        pts.append((cx+rr*math.cos(angle), cy+rr*math.sin(angle)))
    d.polygon(pts, fill=fill)

def draw_bolt(d, box, fill):
    x0,y0,x1,y1 = box
    w = x1-x0; h=y1-y0
    pts = [
        (x0 + 0.40*w, y0 + 0.05*h),
        (x0 + 0.58*w, y0 + 0.05*h),
        (x0 + 0.45*w, y0 + 0.48*h),
        (x0 + 0.65*w, y0 + 0.48*h),
        (x0 + 0.35*w, y0 + 0.95*h),
        (x0 + 0.42*w, y0 + 0.55*h),
        (x0 + 0.28*w, y0 + 0.55*h),
    ]
    d.polygon(pts, fill=fill)

def draw_crown(d, box, fill):
    x0,y0,x1,y1 = box
    w=x1-x0; h=y1-y0
    base_h = y0 + 0.75*h
    pts = [
        (x0+0.12*w, base_h), (x0+0.22*w, y0+0.35*h),
        (x0+0.35*w, base_h), (x0+0.50*w, y0+0.28*h),
        (x0+0.65*w, base_h), (x0+0.78*w, y0+0.35*h),
        (x0+0.88*w, base_h), (x0+0.12*w, base_h)
    ]
    d.polygon(pts, fill=fill)

def draw_flame(d, box, fill):
    x0,y0,x1,y1 = box
    w=x1-x0; h=y1-y0
    pts = [
        (x0+0.50*w, y0+0.10*h),
        (x0+0.65*w, y0+0.28*h),
        (x0+0.58*w, y0+0.48*h),
        (x0+0.75*w, y0+0.65*h),
        (x0+0.50*w, y0+0.90*h),
        (x0+0.25*w, y0+0.65*h),
        (x0+0.42*w, y0+0.48*h),
        (x0+0.35*w, y0+0.28*h),
    ]
    d.polygon(pts, fill=fill)

def draw_wing(d, box, fill):
    x0,y0,x1,y1 = box
    w=x1-x0; h=y1-y0
    # three feather sweeps
    for i,f in enumerate([0.15, 0.32, 0.49]):
        pts = [
            (x0+0.20*w, y0+(0.30+f)*h),
            (x0+0.80*w, y0+(0.10+f)*h),
            (x0+0.55*w, y0+(0.18+f)*h),
        ]
        d.polygon(pts, fill=fill)

def draw_claw(d, box, fill):
    x0,y0,x1,y1 = box
    w=x1-x0; h=y1-y0
    # three slashes
    for i in range(3):
        off = i * (w*0.12)
        d.polygon([
            (x0+0.25*w+off, y0+0.20*h),
            (x0+0.34*w+off, y0+0.18*h),
            (x0+0.75*w+off, y0+0.80*h),
            (x0+0.66*w+off, y0+0.82*h),
        ], fill=fill)

def draw_hammer(d, box, fill):
    x0,y0,x1,y1 = box
    w=x1-x0; h=y1-y0
    # head
    d.rectangle([x0+0.30*w, y0+0.30*h, x0+0.75*w, y0+0.45*h], fill=fill)
    # handle
    d.rectangle([x0+0.45*w, y0+0.45*h, x0+0.55*w, y0+0.80*h], fill=fill)

def draw_shield_chevron(d, box, fill):
    x0,y0,x1,y1 = box
    w=x1-x0; h=y1-y0
    pts = [
        (x0+0.18*w, y0+0.32*h),
        (x0+0.82*w, y0+0.32*h),
        (x0+0.50*w, y0+0.70*h),
    ]
    d.polygon(pts, fill=fill)

# ---- filenames & mapping ----
def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip()) or "team"

def main():
    ap = argparse.ArgumentParser(description="Local description-aware logo generator (no API).")
    ap.add_argument("--from-espn", action="store_true", help="Include ESPN team names from leagues.json")
    ap.add_argument("--force", action="store_true", help="Overwrite existing PNGs")
    ap.add_argument("--out", default="logos/ai", help="Output dir (default: logos/ai)")
    args = ap.parse_args()

    if not ensure_pillow():
        raise SystemExit("Pillow is required. Run: pip install pillow")

    mascots = load_team_mascots()
    names = set(mascots.keys())
    if args.from_espn:
        names |= load_espn_team_names()

    if not names:
        raise SystemExit("No team names found. Add team_mascots.py or use --from-espn with leagues.json.")

    out_dir = Path(args.out)
    mapping_path = Path("team_logos.json")

    # extend existing mapping if present
    mapping: dict[str, str] = {}
    if mapping_path.is_file():
        try:
            mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        except Exception:
            mapping = {}

    created, skipped = 0, 0
    for team in sorted(names):
        fname = safe_filename(team) + ".png"
        dest = out_dir / fname
        if dest.exists() and not args.force:
            mapping[team] = str(dest)
            skipped += 1
            continue
        try:
            draw_logo(team, mascots.get(team), dest)
            mapping[team] = str(dest)
            created += 1
            print(f"[ok] {team} -> {dest}")
        except Exception as e:
            print(f"[warn] {team}: {e}")

    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDone. Created {created}, skipped {skipped}.")
    print(f"Logos dir: {out_dir}")
    print(f"Mapping:   {mapping_path} (consumed by mascots_util.logo_for)")
    
if __name__ == "__main__":
    main()

