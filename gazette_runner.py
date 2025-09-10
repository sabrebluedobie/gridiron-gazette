# gazette_runner.py
# ESPN -> context -> DOCX/PDF with:
# - enumerated MATCHUPi_* fields (scores, mascots, logos, story, art)
# - top-level LEAGUE_LOGO and BUSINESS_LOGO images
# - optional editorial images generation via OpenAI
# - absolute path printing for outputs

import argparse, json, re, subprocess, sys, os
from datetime import date
from pathlib import Path
from typing import Dict, Any, List, Optional

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

from gazette_data import fetch_week_from_espn, build_context
from mascots_util import logo_for  # team logos (auto-discovery)

# Optional OpenAI (used for editorial images if --images)
try:
    from openai import OpenAI
    _OPENAI = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None
except Exception:
    _OPENAI = None

# Try docx2pdf; fallback to LibreOffice
try:
    from docx2pdf import convert  # type: ignore[import-not-found]
except Exception:
    convert = None

# ----------------- helpers -----------------
def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s or "")

def _as_str(v):
    try:
        f = float(v)
        return f"{int(f)}" if f.is_integer() else f"{f:.1f}"
    except Exception:
        return f"{v}" if v is not None else ""

def _resolve_path(p: Optional[str]) -> Optional[str]:
    if not p:
        return None
    pp = Path(p)
    if not pp.is_absolute():
        pp = Path.cwd() / pp
    return str(pp) if pp.is_file() else None

# ----------------- context expansion -----------------
def add_enumerated_matchups(context: Dict[str, Any], max_slots: int = 12) -> None:
    games = context.get("games", []) or []
    for i in range(1, max_slots + 1):
        g = games[i - 1] if i - 1 < len(games) else {}
        context[f"MATCHUP{i}_HOME"] = g.get("home", "") or ""
        context[f"MATCHUP{i}_AWAY"] = g.get("away", "") or ""
        context[f"MATCHUP{i}_HS"]   = _as_str(g.get("hs", ""))
        context[f"MATCHUP{i}_AS"]   = _as_str(g.get("as", ""))
        context[f"MATCHUP{i}_HOME_NAME"] = context[f"MATCHUP{i}_HOME"]
        context[f"MATCHUP{i}_AWAY_NAME"] = context[f"MATCHUP{i}_AWAY"]
        context[f"MATCHUP{i}_HOME_MASCOT"] = g.get("home_mascot", "") or ""
        context[f"MATCHUP{i}_AWAY_MASCOT"] = g.get("away_mascot", "") or ""
        context[f"MATCHUP{i}_TOP_HOME"]    = g.get("home_top", "") or ""
        context[f"MATCHUP{i}_TOP_AWAY"]    = g.get("away_top", "") or ""
        context[f"MATCHUP{i}_BUST"]        = g.get("biggest_bust", "") or ""
        context[f"MATCHUP{i}_KEYPLAY"]     = g.get("key_play", "") or ""
        context[f"MATCHUP{i}_DEF"]         = g.get("defense_note", "") or ""
        context[f"MATCHUP{i}_BLURB"]       = g.get("blurb", "") or ""
        # story + prompts (from storymaker via gazette_data)
        context[f"MATCHUP{i}_STORY"]       = g.get("story", "") or ""
        context[f"MATCHUP{i}_ART_PROMPT"]  = g.get("article_prompt", "") or ""
        context[f"MATCHUP{i}_BADGE_PROMPT"]= g.get("badge_prompt", "") or ""

def add_team_logo_images(context: Dict[str, Any], doc: DocxTemplate, max_slots: int = 12, width_mm: float = 18.0) -> None:
    for i in range(1, max_slots + 1):
        home = context.get(f"MATCHUP{i}_HOME", "")
        away = context.get(f"MATCHUP{i}_AWAY", "")
        hp = logo_for(home)
        ap = logo_for(away)
        context[f"MATCHUP{i}_HOME_LOGO"] = InlineImage(doc, hp, width=Mm(width_mm)) if hp else ""
        context[f"MATCHUP{i}_AWAY_LOGO"] = InlineImage(doc, ap, width=Mm(width_mm)) if ap else ""

# ----------------- branding (league/sponsor) -----------------
_DEFAULT_BRANDING_CANDIDATES = [
    "assets/branding/league_logo.png",
    "assets/branding/league_logo.jpg",
    "logos/branding/league_logo.png",
    "logos/branding/league_logo.jpg",
    "assets/branding/sponsor_logo.png",
    "assets/branding/sponsor_logo.jpg",
]

def _find_default(path_list: List[str]) -> Optional[str]:
    for p in path_list:
        rp = _resolve_path(p)
        if rp:
            return rp
    return None

def add_branding_images(context: Dict[str, Any], doc: DocxTemplate,
                        league_logo_path: Optional[str],
                        business_logo_path: Optional[str],
                        league_logo_mm: float,
                        business_logo_mm: float) -> None:
    """
    Insert LEAGUE_LOGO and BUSINESS_LOGO as InlineImage if available.
    Precedence:
      - explicit CLI flag
      - leagues.json fields: league_logo and sponsor.logo
      - default search under assets/branding or logos/branding
    """
    # Try explicit args first (already resolved below)
    league_path = _resolve_path(league_logo_path)
    bus_path = _resolve_path(business_logo_path)

    # If missing, look in context (from leagues.json)
    if not league_path:
        league_path = _resolve_path(context.get("league_logo_path"))
    if not bus_path:
        bus_path = _resolve_path(context.get("sponsor_logo_path"))

    # Fallback defaults
    if not league_path:
        league_path = _find_default([
            "assets/branding/league_logo.png",
            "assets/branding/league_logo.jpg",
            "logos/branding/league_logo.png",
            "logos/branding/league_logo.jpg",
        ])
    if not bus_path:
        bus_path = _find_default([
            "assets/branding/sponsor_logo.png",
            "assets/branding/sponsor_logo.jpg",
            "logos/branding/sponsor_logo.png",
            "logos/branding/sponsor_logo.jpg",
        ])

    context["LEAGUE_LOGO"] = InlineImage(doc, league_path, width=Mm(league_logo_mm)) if league_path else ""
    context["BUSINESS_LOGO"] = InlineImage(doc, bus_path, width=Mm(business_logo_mm)) if bus_path else ""

# ----------------- editorial images (optional) -----------------
def _gen_editorial_image(prompt: str, out_path: Path, size="1024x1024") -> bool:
    if not _OPENAI:
        return False
    try:
        r = _OPENAI.images.generate(model="gpt-image-1", prompt=prompt, size=size)
        import base64
        b64 = r.data[0].b64_json
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(b64))
        return True
    except Exception:
        return False

def add_article_images(context: Dict[str, Any], doc: DocxTemplate, league: str, out_root: str,
                       max_slots: int = 12, width_mm: float = 60.0, render: bool = False) -> None:
    for i in range(1, max_slots + 1):
        prompt = context.get(f"MATCHUP{i}_ART_PROMPT", "")
        home = context.get(f"MATCHUP{i}_HOME", "")
        away = context.get(f"MATCHUP{i}_AWAY", "")
        if not home or not away:
            context[f"MATCHUP{i}_ARTIMG"] = ""
            continue
        safe_week = _safe(context.get("week", "Week"))
        day = context.get("date") or date.today().isoformat()
        art_dir = Path(out_root) / _safe(context.get("league","League")) / day / "images"
        img_path = art_dir / f"Article_{i}_{_safe(home)}_vs_{_safe(away)}_{safe_week}.png"

        if img_path.is_file():
            ok = True
        elif render and prompt:
            ok = _gen_editorial_image(prompt, img_path)
        else:
            ok = False

        context[f"MATCHUP{i}_ARTIMG"] = InlineImage(doc, str(img_path), width=Mm(width_mm)) if ok else ""

# ----------------- rendering -----------------
def render_docx(context: Dict[str, Any], template="recap_template.docx",
                out_root="recaps", slots: int = 12,
                logo_mm: float = 18.0, art_mm: float = 60.0, render_images=False,
                league_logo_path: Optional[str] = None, business_logo_path: Optional[str] = None,
                league_logo_mm: float = 38.0, business_logo_mm: float = 30.0) -> str:
    add_enumerated_matchups(context, max_slots=slots)

    league = context.get("league", "League")
    day = context.get("date") or date.today().isoformat()
    week = _safe(context.get("week", "Week"))
    out_dir = Path(out_root) / _safe(league) / day
    out_dir.mkdir(parents=True, exist_ok=True)

    docx_path = out_dir / f"Gazette_{week}.docx"
    doc = DocxTemplate(template)

    # Team logos in matchups
    add_team_logo_images(context, doc, max_slots=slots, width_mm=logo_mm)
    # League + sponsor branding
    add_branding_images(context, doc, league_logo_path, business_logo_path, league_logo_mm, business_logo_mm)
    # Editorial art per matchup
    add_article_images(context, doc, league=league, out_root=out_root,
                       max_slots=slots, width_mm=art_mm, render=render_images)

    doc.render(context)
    doc.save(str(docx_path))
    return str(docx_path)

def to_pdf(docx_path: str) -> str:
    pdf_path = str(Path(docx_path).with_suffix(".pdf"))
    if convert is not None:
        try:
            convert(docx_path, pdf_path)
            return pdf_path
        except Exception:
            pass
    try:
        outdir = str(Path(pdf_path).parent)
        subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", "--outdir", outdir, docx_path],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return pdf_path
    except Exception:
        print("[warn] PDF export skipped (no docx2pdf or soffice).")
        return ""

# ----------------- flow -----------------
def run_single(cfg: Dict[str, Any], args) -> List[str]:
    games = fetch_week_from_espn(
        league_id=cfg["league_id"], year=cfg["year"],
        ***REMOVED***
        week=args.week
    )
    if not games:
        print(f"[warn] No games returned for {cfg.get('name')} (week={args.week or 'current'}). "
              f"If private, ensure espn_s2/SWID cookies in leagues.json.")
    ctx = build_context(cfg, games)

    # Optional overrides
    if args.week_label:
        ctx["week"] = args.week_label
        ctx["title"] = f'{ctx["league"]} — {args.week_label}'
    if args.date:
        ctx["date"] = args.date

    # Provide branding paths via context so render_docx can pick them up too
    # leagues.json can include: "league_logo": "path", "sponsor": {"name":"...", "logo":"path", "line":"..."}
    if cfg.get("league_logo"):
        ctx["league_logo_path"] = cfg["league_logo"]
    sponsor = cfg.get("sponsor") or {}
    if sponsor.get("logo"):
        ctx["sponsor_logo_path"] = sponsor["logo"]

    out_docx = render_docx(
        ctx,
        template=args.template,
        out_root=args.out_dir,
        slots=args.slots,
        logo_mm=args.logo_mm,
        art_mm=args.art_mm,
        render_images=args.images,
        league_logo_path=args.league_logo,
        business_logo_path=args.business_logo,
        league_logo_mm=args.league_logo_mm,
        business_logo_mm=args.business_logo_mm,
    )
    outputs = [out_docx]
    if args.pdf:
        pdf = to_pdf(out_docx)
        if pdf:
            outputs.append(pdf)
    return outputs

def main():
    ap = argparse.ArgumentParser(description="Gridiron Gazette (mascot-driven stories + images + branding).")
    ap.add_argument("--leagues", default="leagues.json")
    ap.add_argument("--template", default="recap_template.docx")
    ap.add_argument("--out-dir", default="recaps")
    ap.add_argument("--pdf", action="store_true", help="Also export PDF")
    ap.add_argument("--images", action="store_true", help="Render editorial images via OpenAI")
    ap.add_argument("--multi", action="store_true", help="Process all leagues in leagues.json")
    ap.add_argument("--league", help="Run only this league by name")
    ap.add_argument("--week", type=int, help="Override ESPN week (default: current)")
    ap.add_argument("--week-label", help='Visible label, e.g. "Week 1 (Sep 13–15, 2025)"')
    ap.add_argument("--date", help='Folder date (default: today, e.g., "2025-09-15")')
    ap.add_argument("--slots", type=int, default=12, help="How many MATCHUPi_* slots exist in the template")
    ap.add_argument("--logo-mm", type=float, default=18.0, help="Logo width (mm) for team logos")
    ap.add_argument("--art-mm", type=float, default=60.0, help="Image width (mm) for editorial art")
    # NEW: branding flags
    ap.add_argument("--league-logo", help="Path to league logo (overrides leagues.json)")
    ap.add_argument("--business-logo", help="Path to sponsor/business logo (overrides leagues.json)")
    ap.add_argument("--league-logo-mm", type=float, default=38.0, help="Width (mm) for LEAGUE_LOGO")
    ap.add_argument("--business-logo-mm", type=float, default=30.0, help="Width (mm) for BUSINESS_LOGO")
    args = ap.parse_args()

    try:
        with open(args.leagues, "r") as f:
            leagues = json.load(f)
    except Exception as e:
        sys.exit(f"Failed to load {args.leagues}: {e}")

    outputs: List[str] = []
    if args.league:
        cfg = next((x for x in leagues if x.get("name") == args.league), None)
        if not cfg:
            names = ", ".join(x.get("name", "?") for x in leagues)
            sys.exit(f'No league named "{args.league}" in {args.leagues}. Known: {names}')
        outputs += run_single(cfg, args)
    else:
        items = leagues if args.multi else leagues[:1]
        for cfg in items:
            outputs += run_single(cfg, args)

    print("\nGenerated files (absolute paths):")
    for p in outputs:
        print(" •", str(Path(p).resolve()))

if __name__ == "__main__":
    main()