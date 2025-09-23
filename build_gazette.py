#!/usr/bin/env python3
"""
build_gazette.py — resilient runner (no hard fail on starters)

Secrets:   ESPN_S2, SWID, OPENAI_API_KEY
Variables: LEAGUE_ID, YEAR, TEMPLATE, OUTDOCX, FANTASY_SEASON_START
"""

import argparse, os, sys, logging
from datetime import datetime
from typing import Optional, Dict, List

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    import yaml
except Exception:
    yaml = None

try:
    from espn_api.football import League
except Exception as e:
    print("❌ Missing dependency: espn_api. `pip install espn-api`", file=sys.stderr)
    raise

import updated_weekly_recap as weekly_recap

LOG = logging.getLogger("build_gazette")

def _env(name: str) -> Optional[str]:
    v = os.getenv(name)
    return v.strip() if isinstance(v, str) and v.strip() else None

def _load_yaml_defaults(path: str = "gazette.yml"):
    if not yaml or not os.path.exists(path): return {}
    try:
        data = yaml.safe_load(open(path, "r", encoding="utf-8")) or {}
        return {str(k).strip().lower(): v for k, v in (data.items() if isinstance(data, dict) else [])}
    except Exception:
        return {}

def _resolve_default(cfg, env_name, cfg_key, fallback):
    return _env(env_name) or cfg.get(cfg_key, fallback)

def _resolve_cookies(cli_s2: Optional[str], cli_swid: Optional[str]) -> Dict[str, str]:
    s2 = cli_s2 or _env("ESPN_S2")
    swid = cli_swid or (_env("SWID") or _env("ESPN_SWID"))
    def ok(v): return f"present (len={len(v)})" if v else "missing"
    print(f"[env] ESPN_S2:{ok(_env('ESPN_S2'))}  SWID:{ok(_env('SWID') or _env('ESPN_SWID'))}")
    print(f"[cli] --s2:{ok(cli_s2)}  --swid:{ok(cli_swid)}")
    if not s2 or not swid:
        raise RuntimeError(
            "❌ Missing ESPN cookies. Provide --s2/--swid, or set ESPN_S2 and SWID.\n"
            "Without them, blurbs may downgrade; doc will still build from YAML if needed."
        )
    if "{" not in swid or "}" not in swid:
        LOG.warning("⚠️ SWID usually includes braces, e.g. {XXXXXXXX-XXXX-...}")
    return {"s2": s2, "swid": swid}

def _parse_args(argv: List[str]) -> argparse.Namespace:
    cfg = _load_yaml_defaults()
    def d(env, key, fb): return _resolve_default(cfg, env, key, fb)
    p = argparse.ArgumentParser(description="Build the Gridiron Gazette recap document.")
    p.add_argument("--league", type=int, default=int(d("LEAGUE_ID","league_id",887998)))
    p.add_argument("--year",   type=int, default=int(d("YEAR","year", datetime.now().year)))
    p.add_argument("--week",   type=int, default=int(d("WEEK","week", 0)))
    p.add_argument("--auto-week", action="store_true", default=bool(cfg.get("auto_week", False)))
    p.add_argument("--week-offset", type=int, default=int(cfg.get("week_offset", 0)))
    p.add_argument("--s2", type=str, default=None)
    p.add_argument("--swid", type=str, default=None)
    p.add_argument("--template",   type=str, default=str(d("TEMPLATE","template","recap_template.docx")))
    p.add_argument("--output-dir", type=str, default=str(d("OUTDOCX","output_dir","recaps")))
    p.add_argument("--llm-blurbs", action="store_true", default=bool(_env("LLM_BLURBS") or cfg.get("llm_blurbs", False)))
    p.add_argument("--blurb-style", default=str(d("BLURB_STYLE","blurb_style","sabre")))
    p.add_argument("--blurb-words", type=int, default=int(d("BLURB_WORDS","blurb_words",200)))
    p.add_argument("--verbose", action="store_true", default=bool(_env("VERBOSE") or cfg.get("verbose", False)))
    args = p.parse_args(argv)
    if cfg.get("league_display_name") and not _env("LEAGUE_DISPLAY_NAME"):
        os.environ["LEAGUE_DISPLAY_NAME"] = str(cfg["league_display_name"])
    return args

def _infer_week(auto_week: bool, week: int, offset: int) -> int:
    if week and not auto_week: return week
    # optional FANTASY_SEASON_START
    start = _env("FANTASY_SEASON_START")
    if start:
        for fmt in ("%Y-%m-%d","%Y/%m/%d","%Y-%m-%dT%H:%M:%S","%Y-%m-%dT%H:%M:%S%z"):
            try:
                from datetime import datetime
                days = (datetime.now() - datetime.strptime(start, fmt)).days
                return max(1, min(18, (days // 7) + 1 + (offset or 0)))
            except Exception:
                pass
    base = datetime.now().isocalendar().week % 18 or 1
    return min(18, max(1, base + (offset or 0)))

def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s: %(message)s")

    cookies = _resolve_cookies(args.s2, args.swid)
    # Build League, but DO NOT hard-fail if starters aren’t accessible.
    league = None
    try:
        league = League(league_id=args.league, year=args.year, espn_s2=cookies["s2"], swid=cookies["swid"])
    except Exception as e:
        LOG.warning("Could not initialize League with cookies: %s. Will build from HTTP/YAML fallback.", e)

    week = _infer_week(args.auto_week or args.week == 0, args.week, args.week_offset)
    LOG.info("Using week=%s", week)

    outdoc = weekly_recap.build_weekly_recap(
        league=league,                 # may be None
        league_id=args.league,
        year=args.year,
        week=week,
        template=args.template,
        output_dir=args.output_dir,    # can be dir or *.docx filename now
        llm_blurbs=args.llm_blurbs,
        blurb_style=args.blurb_style,
        blurb_words=args.blurb_words
    )
    print(f"✅ Recap generated: {outdoc}")
    print("🎉 Build complete.")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        LOG.exception("Build failed: %s", e)
        raise SystemExit(1)
