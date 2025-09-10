cat > gazette_runner.py <<'PY'
# gazette_runner.py  — branding + stories + optional images + PDF
import argparse, json, re, subprocess, sys, os
from datetime import date
from pathlib import Path
from typing import Dict, Any, List, Optional
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
from gazette_data import fetch_week_from_espn, build_context
from mascots_util import logo_for

try:
    from openai import OpenAI
    _OPENAI = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None
except Exception:
    _OPENAI = None

try:
    from docx2pdf import convert  # type: ignore[import-not-found]
except Exception:
    convert = None

def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s or "")

def _as_str(v):
    try:
        f = float(v);  return f"{int(f)}" if f.is_integer() else f"{f:.1f}"
    except Exception:
        return f"{v}" if v is not None else ""

def _resolve_path(p: Optional[str]) -> Optional[str]:
    if not p: return None
    pp = Path(p);  pp = pp if pp.is_absolute() else (Path.cwd()/pp)
    return str(pp) if pp.is_file() else None

def add_enumerated_matchups(ctx: Dict[str, Any], max_slots: int = 12) -> None:
    games = ctx.get("games", []) or []
    for i in range(1, max_slots+1):
        g = games[i-1] if i-1 < len(games) else {}
        ctx[f"MATCHUP{i}_HOME"] = g.get("home","") or ""
        ctx[f"MATCHUP{i}_AWAY"] = g.get("away","") or ""
        ctx[f"MATCHUP{i}_HS"]   = _as_str(g.get("hs",""))
        ctx[f"MATCHUP{i}_AS"]   = _as_str(g.get("as",""))
        ctx[f"MATCHUP{i}_HOME_NAME"]=ctx[f"MATCHUP{i}_HOME"]
        ctx[f"MATCHUP{i}_AWAY_NAME"]=ctx[f"MATCHUP{i}_AWAY"]
        ctx[f"MATCHUP{i}_HOME_MASCOT"]=g.get("home_mascot","") or ""
        ctx[f"MATCHUP{i}_AWAY_MASCOT"]=g.get("away_mascot","") or ""
        ctx[f"MATCHUP{i}_TOP_HOME"]=g.get("home_top","") or ""
        ctx[f"MATCHUP{i}_TOP_AWAY"]=g.get("away_top","") or ""
        ctx[f"MATCHUP{i}_BUST"]=g.get("biggest_bust","") or ""
        ctx[f"MATCHUP{i}_KEYPLAY"]=g.get("key_play","") or ""
        ctx[f"MATCHUP{i}_DEF"]=g.get("defense_note","") or ""
        ctx[f"MATCHUP{i}_BLURB"]=g.get("blurb","") or ""
        ctx[f"MATCHUP{i}_STORY"]=g.get("story","") or ""
        ctx[f"MATCHUP{i}_ART_PROMPT"]=g.get("article_prompt","") or ""
        ctx[f"MATCHUP{i}_BADGE_PROMPT"]=g.get("badge_prompt","") or ""

def add_team_logo_images(ctx: Dict[str, Any], doc: DocxTemplate, slots=12, width_mm=18.0):
    for i in range(1, slots+1):
        home = ctx.get(f"MATCHUP{i}_HOME","");  away = ctx.get(f"MATCHUP{i}_AWAY","")
        hp = logo_for(home);  ap = logo_for(away)
        ctx[f"MATCHUP{i}_HOME_LOGO"] = InlineImage(doc, hp, width=Mm(width_mm)) if hp else ""
        ctx[f"MATCHUP{i}_AWAY_LOGO"] = InlineImage(doc, ap, width=Mm(width_mm)) if ap else ""

def add_branding_images(ctx: Dict[str, Any], doc: DocxTemplate,
                        league_logo_path: Optional[str], business_logo_path: Optional[str],
                        league_logo_mm: float, business_logo_mm: float):
    league_path = _resolve_path(league_logo_path) or _resolve_path(ctx.get("league_logo_path"))
    biz_path    = _resolve_path(business_logo_path) or _resolve_path(ctx.get("sponsor_logo_path"))
    if not league_path:
        for p in ["assets/branding/league_logo.png","assets/branding/league_logo.jpg",
                  "logos/branding/league_logo.png","logos/branding/league_logo.jpg"]:
            league_path = _resolve_path(p);  if league_path: break
    if not biz_path:
        for p in ["assets/branding/sponsor_logo.png","assets/branding/sponsor_logo.jpg",
                  "logos/branding/sponsor_logo.png","logos/branding/sponsor_logo.jpg"]:
            biz_path = _resolve_path(p);  if biz_path: break
    ctx["LEAGUE_LOGO"]   = InlineImage(doc, league_path, width=Mm(league_logo_mm)) if league_path else ""
    ctx["BUSINESS_LOGO"] = InlineImage(doc, biz_path,    width=Mm(business_logo_mm)) if biz_path else ""

def _gen_editorial_image(prompt: str, out_path: Path, size="1024x1024") -> bool:
    if not _OPENAI: return False
    try:
        r = _OPENAI.images.generate(model="gpt-image-1", prompt=prompt, size=size)
        import base64
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path,"wb") as f: f.write(base64.b64decode(r.data[0].b64_json))
        return True
    except Exception:
        return False

def add_article_images(ctx: Dict[str, Any], doc: DocxTemplate, out_root: str, slots=12, width_mm=60.0, render=False):
    for i in range(1, slots+1):
        prompt = ctx.get(f"MATCHUP{i}_ART_PROMPT","")
        home = ctx.get(f"MATCHUP{i}_HOME","");  away = ctx.get(f"MATCHUP{i}_AWAY","")
        if not home or not away:
            ctx[f"MATCHUP{i}_ARTIMG"] = "";  continue
        safe_week = _safe(ctx.get("week","Week"))
        day = ctx.get("date") or date.today().isoformat()
        art_dir = Path(out_root) / _safe(ctx.get("league","League")) / day / "images"
        img_path = art_dir / f"Article_{i}_{_safe(home)}_vs_{_safe(away)}_{safe_week}.png"
        ok = img_path.is_file() or (render and prompt and _gen_editorial_image(prompt, img_path))
        ctx[f"MATCHUP{i}_ARTIMG"] = InlineImage(doc, str(img_path), width=Mm(width_mm)) if ok else ""

def render_docx(ctx: Dict[str, Any], template="recap_template.docx",
                out_root="recaps", slots=12, logo_mm=18.0, art_mm=60.0, render_images=False,
                league_logo_path=None, business_logo_path=None, league_logo_mm=38.0, business_logo_mm=30.0) -> str:
    add_enumerated_matchups(ctx, slots)
    league = ctx.get("league","League"); day = ctx.get("date") or date.today().isoformat()
    week = _safe(ctx.get("week","Week"))
    out_dir = Path(out_root) / _safe(league) / day;  out_dir.mkdir(parents=True, exist_ok=True)
    docx_path = out_dir / f"Gazette_{week}.docx"
    doc = DocxTemplate(template)
    add_team_logo_images(ctx, doc, slots, logo_mm)
    add_branding_images(ctx, doc, league_logo_path, business_logo_path, league_logo_mm, business_logo_mm)
    add_article_images(ctx, doc, out_root, slots, art_mm, render_images)
    doc.render(ctx);  doc.save(str(docx_path))
    return str(docx_path)

def to_pdf(docx_path: str) -> str:
    pdf_path = str(Path(docx_path).with_suffix(".pdf"))
    if convert is not None:
        try: convert(docx_path, pdf_path);  return pdf_path
        except Exception: pass
    try:
        outdir = str(Path(pdf_path).parent)
        subprocess.run(["soffice","--headless","--convert-to","pdf","--outdir",outdir,docx_path],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return pdf_path
    except Exception:
        print("[warn] PDF export skipped (no docx2pdf or soffice).");  return ""

def run_single(cfg: Dict[str, Any], args) -> List[str]:
    games = fetch_week_from_espn(cfg["league_id"], cfg["year"], cfg.get("espn_s2",""), cfg.get("swid",""), args.week)
    if not games:
        print(f"[warn] No games returned for {cfg.get('name')} (week={args.week or 'current'}). "
              f"If private, ensure espn_s2/SWID cookies in leagues.json.")
    ctx = build_context(cfg, games)
    if args.week_label: ctx["week"]=args.week_label;  ctx["title"]=f'{ctx["league"]} — {args.week_label}'
    if args.date: ctx["date"]=args.date
    if cfg.get("league_logo"): ctx["league_logo_path"]=cfg["league_logo"]
    if (cfg.get("sponsor") or {}).get("logo"): ctx["sponsor_logo_path"]=cfg["sponsor"]["logo"]
    out_docx = render_docx(ctx, template=args.template, out_root=args.out_dir, slots=args.slots,
                           logo_mm=args.logo_mm, art_mm=args.art_mm, render_images=args.images,
                           league_logo_path=args.league_logo, business_logo_path=args.business_logo,
                           league_logo_mm=args.league_logo_mm, business_logo_mm=args.business_logo_mm)
    outs=[out_docx];  if args.pdf: 
        pdf=to_pdf(out_docx);  outs.append(pdf) if pdf else None
    return outs

def main():
    ap = argparse.ArgumentParser(description="Gridiron Gazette (branding + stories + images).")
    ap.add_argument("--leagues", default="leagues.json")
    ap.add_argument("--template", default="recap_template.docx")
    ap.add_argument("--out-dir", default="recaps")
    ap.add_argument("--pdf", action="store_true")
    ap.add_argument("--images", action="store_true")
    ap.add_argument("--multi", action="store_true")
    ap.add_argument("--league")
    ap.add_argument("--week", type=int)
    ap.add_argument("--week-label")
    ap.add_argument("--date")
    ap.add_argument("--slots", type=int, default=12)
    ap.add_argument("--logo-mm", type=float, default=18.0)
    ap.add_argument("--art-mm", type=float, default=60.0)
    # NEW branding flags
    ap.add_argument("--league-logo")
    ap.add_argument("--business-logo")
    ap.add_argument("--league-logo-mm", type=float, default=38.0)
    ap.add_argument("--business-logo-mm", type=float, default=30.0)
    args = ap.parse_args()

    with open(args.leagues,"r") as f:
        leagues = json.load(f)

    outputs: List[str] = []
    if args.league:
        cfg = next((x for x in leagues if x.get("name")==args.league), None)
        if not cfg:
            names=", ".join(x.get("name","?") for x in leagues)
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
PY