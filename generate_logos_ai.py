#!/usr/bin/env python3
"""
Generate AI logo images using mascot descriptions as the creative brief.

Sources for team names/descriptions:
  - team_mascots.py (team_mascots: {team_name: mascot_description})
  - optional: ESPN teams from leagues.json via --from-espn (names only; description may be missing)

Output:
  - PNG files in logos/ai/
  - team_logos.json mapping { "<Exact Team Name>": "logos/ai/<file>.png" }

Usage:
  export ***REMOVED***
  python3 generate_logos_ai.py                # from team_mascots only
  python3 generate_logos_ai.py --from-espn    # include ESPN team_name set
  python3 generate_logos_ai.py --force        # overwrite existing images
"""

from __future__ import annotations
import argparse, base64, json, os, re, time, hashlib
from pathlib import Path

# -------- helpers: load sources --------
def load_team_mascots() -> dict[str, str]:
    try:
        import team_mascots as TM
        if hasattr(TM, "team_mascots") and isinstance(TM.team_mascots, dict):
            return dict(TM.team_mascots)
    except Exception:
        pass
    # optional JSON fallback
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
                L = League(
                    league_id=c["league_id"], year=c["year"],
                    ***REMOVED***
                )
                for t in L.teams:
                    names.add(t.team_name)
            except Exception:
                continue
    except Exception:
        pass
    return names

# -------- prompt building --------
def initials(name: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", name)
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    s = re.sub(r"[^A-Za-z0-9]", "", name).upper()
    return (s[:2] or "T")

def primary_hex(name: str) -> str:
    h = hashlib.md5(name.encode("utf-8")).hexdigest()
    r = int(h[0:2], 16); g = int(h[2:4], 16); b = int(h[4:6], 16)
    # nudge toward brighter palette
    r = 90 + int(r * 0.6); g = 90 + int(g * 0.6); b = 90 + int(b * 0.6)
    return f"#{r:02X}{g:02X}{b:02X}"

def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip()) or "team"

def build_prompt(team: str, desc: str | None) -> str:
    init = initials(team)
    color = primary_hex(team)
    return (
        "Create an original, flat vector-style sports logo for a FANTASY football team.\n"
        f"Team name: {team}\n"
        f"Mascot concept (use as creative brief): {desc or 'no description provided'}\n\n"
        "Design directives:\n"
        "- Clean, bold silhouette; minimal detail; strong contrast; avoid photorealism.\n"
        "- One emblem/badge (circle/shield/crest). Symmetry preferred.\n"
        f"- Color palette anchored by primary {color}; up to two neutral accents.\n"
        f"- No real text; optional subtle initials '{init}' if it improves the mark.\n"
        "- No copyrighted/pro sports marks. Original design only.\n"
        "- Transparent background."
    )

# -------- OpenAI client --------
def get_client():
    try:
        from openai import OpenAI
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("Set OPENAI_API_KEY in your environment.")
        return OpenAI(api_key=key)
    except Exception as e:
        raise SystemExit(f"OpenAI client unavailable: {e}")

def generate_logo_png(client, prompt: str, dest: Path, size="1024x1024", transparent=True):
    # gpt-image-1 supports background="transparent"
    params = {
        "model": "gpt-image-1",
        "prompt": prompt,
        "size": size,
    }
    if transparent:
        params["background"] = "transparent"

    resp = client.images.generate(**params)
    b64 = resp.data[0].b64_json
    img_bytes = base64.b64decode(b64)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(img_bytes)

# -------- main flow --------
def main():
    ap = argparse.ArgumentParser(description="Generate AI logos using mascot descriptions.")
    ap.add_argument("--from-espn", action="store_true", help="Include team names from leagues.json via espn_api")
    ap.add_argument("--force", action="store_true", help="Overwrite existing files")
    ap.add_argument("--out", default="logos/ai", help="Output directory for PNGs")
    ap.add_argument("--delay", type=float, default=0.7, help="Seconds between API calls")
    args = ap.parse_args()

    client = get_client()

    mascots = load_team_mascots()   # {team: description}
    names = set(mascots.keys())
    if args.from_espn:
        names |= load_espn_team_names()

    if not names:
        raise SystemExit("No team names found. Add team_mascots.py or use --from-espn with a valid leagues.json.")

    out_dir = Path(args.out)
    mapping_path = Path("team_logos.json")
    # start from existing mapping if present
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

        prompt = build_prompt(team, mascots.get(team))
        try:
            generate_logo_png(client, prompt, dest)
            mapping[team] = str(dest)
            created += 1
            print(f"[ok] {team} -> {dest}")
            time.sleep(args.delay)
        except Exception as e:
            print(f"[warn] {team}: {e}")

    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDone. Created {created}, skipped {skipped}.")
    print(f"Logos dir: {out_dir}")
    print(f"Mapping:   {mapping_path} (used by mascots_util.py)")
    
if __name__ == "__main__":
    main()
