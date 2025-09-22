#!/usr/bin/env python3
"""
build_gazette.py — Gridiron Gazette runner (fail-fast + CLI cookies + Sabre voice)

Features
- Fails fast if ESPN cookies are missing.
- Supports CLI cookies: --s2 and --swid (no need for .env locally).
- Still works with ENV (GitHub Actions secrets) and loads .env if present.
- Safe debug prints to verify cookies are detected without exposing values.
- Optional LLM blurbs with --llm-blurbs and style selection (default: sabre).

Requires:
  pip install espn-api python-dotenv
  (and openai in storymaker.py if using --llm-blurbs)
"""

import argparse
import os
import sys
import logging
from datetime import datetime
from typing import Optional, Dict, List

# Optional .env (local dev). In Actions, ENV comes from secrets.
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

# ESPN API
try:
    from espn_api.football import League  # type: ignore
except Exception as e:
    print("❌ Missing dependency: espn_api. Run `pip install espn-api`.", file=sys.stderr)
    raise

# Project modules (kept loose so you can organize your repo as you like)
try:
    import weekly_recap
except Exception:
    weekly_recap = None
try:
    import storymaker
except Exception:
    storymaker = None

LOG = logging.getLogger("build_gazette")


def get_env(name: str) -> Optional[str]:
    v = os.getenv(name)
    if v is not None and isinstance(v, str):
        v = v.strip()
    return v or None


def resolve_cookies(cli_s2: Optional[str], cli_swid: Optional[str]) -> Dict[str, str]:
    """
    Priority: CLI > ENV (ESPN_S2/S2, ESPN_SWID/SWID).  No secrets printed.
    """
    s2 = cli_s2 or get_env("ESPN_S2") or get_env("S2")
    swid = cli_swid or get_env("ESPN_SWID") or get_env("SWID")

    def safe_len(v: Optional[str]) -> str:
        return f"present (len={len(v)})" if v else "missing"

    print(f"Env check  ESPN_S2:{safe_len(get_env('ESPN_S2'))}  S2:{safe_len(get_env('S2'))}")
    print(f"Env check  ESPN_SWID:{safe_len(get_env('ESPN_SWID'))}  SWID:{safe_len(get_env('SWID'))}")
    print(f"CLI flags  --s2:{safe_len(cli_s2)}  --swid:{safe_len(cli_swid)}")

    if not s2 or not swid:
        raise RuntimeError(
            "❌ Missing ESPN cookies. Provide --s2/--swid, or set ESPN_S2/ESPN_SWID in the environment.\n"
            "Without them, player stats, awards, logos, and blurbs cannot be generated."
        )
    if "{" not in swid or "}" not in swid:
        LOG.warning("⚠️ ESPN_SWID typically includes braces, e.g. {XXXXXXXX-XXXX-...}")

    return {"s2": s2, "swid": swid}


def ensure_player_access(league: "League", week: int) -> None:
    """
    Sanity check that we truly have private data (starters/box scores).
    """
    try:
        matchups = league.scoreboard(week)
        if not matchups:
            LOG.warning("No matchups returned for week=%s. Continuing.", week)
            return
        m0 = matchups[0]
        starters = getattr(getattr(m0, "home_team", None), "starters", None)
        if starters is None:
            raise RuntimeError("No starters returned; cookies may be invalid or not passed to the process.")
    except Exception as e:
        raise RuntimeError("❌ Could not access player-level data (box scores/starters). Check cookies.") from e


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build the Gridiron Gazette recap document.")
    p.add_argument("--league", type=int, default=int(get_env("LEAGUE_ID") or 887998), help="ESPN League ID")
    p.add_argument("--year", type=int, default=int(get_env("YEAR") or datetime.now().year), help="Season year")
    p.add_argument("--week", type=int, default=int(get_env("WEEK") or 0), help="Week number; 0 = auto by ISO-approx")
    p.add_argument("--auto-week", action="store_true", help="Infer current week if --week=0")
    p.add_argument("--week-offset", type=int, default=0, help="Offset to add to inferred week")

    # Cookies via CLI (avoids local .env)
    p.add_argument("--s2", type=str, default=None, help="ESPN S2 cookie (espn_s2)")
    p.add_argument("--swid", type=str, default=None, help="ESPN SWID cookie (with braces)")

    p.add_argument("--template", type=str, default=get_env("TEMPLATE") or get_env("GAZETTE_TEMPLATE") or "",
                   help="Path to recap_template.docx")
    p.add_argument("--output-dir", type=str, default=get_env("OUTDOCX_DIR") or get_env("GAZETTE_OUTDIR") or "recaps",
                   help="Output directory")

    # Blurbs
    p.add_argument("--llm-blurbs", action="store_true", help="Generate LLM blurbs")
    p.add_argument("--blurb-style", default=get_env("BLURB_STYLE") or "sabre", help="Blurb voice/style key")
    p.add_argument("--blurb-words", type=int, default=int(get_env("BLURB_WORDS") or 200), help="Approx words per blurb")

    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    return p.parse_args(argv)


def infer_week(auto_week: bool, week: int, offset: int) -> int:
    if week and week > 0 and not auto_week:
        return week
    # very rough ISO-based rolling window (safer than utcnow deprecation)
    base = datetime.now().isocalendar().week % 18
    base = base or 1
    w = max(1, base + (offset or 0))
    return min(18, w)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s: %(message)s")

    cookies = resolve_cookies(args.s2, args.swid)
    league = League(league_id=args.league, year=args.year, espn_s2=cookies["s2"], swid=cookies["swid"])

    week = infer_week(args.auto_week or args.week == 0, args.week, args.week_offset)
    LOG.info("Using week=%s", week)

    ensure_player_access(league, week)

    if weekly_recap is None or not hasattr(weekly_recap, "build_weekly_recap"):
        raise RuntimeError("weekly_recap.build_weekly_recap not found in your repo.")

    outdoc = weekly_recap.build_weekly_recap(
        league=league,
        year=args.year,
        week=week,
        template=(args.template or None),
        output_dir=args.output_dir
    )
    print(f"✅ Recap generated: {outdoc}")

    if args.llm_blurbs:
        if storymaker is None or not hasattr(storymaker, "generate_blurbs"):
            raise RuntimeError("storymaker.generate_blurbs not found in your repo.")
        blurbs = storymaker.generate_blurbs(
            league=league, year=args.year, week=week,
            style=args.blurb_style, max_words=args.blurb_words
        )
        print(f"✅ Blurbs generated: {len(blurbs)}")
    else:
        print("⏩ Skipping blurbs (flag not set)")

    print("🎉 Build complete.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)
    except Exception as e:
        LOG.exception("Unhandled error: %s", e)
        raise SystemExit(2)
