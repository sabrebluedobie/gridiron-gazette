#!/usr/bin/env python3
"""
build_gazette.py — Gridiron Gazette runner (clean, fail-fast, template-ready)

- Fails fast if ESPN cookies are missing (works with GitHub Actions secrets).
- Accepts CLI cookies (--s2/--swid) to avoid local .env if you prefer.
- Creates an espn_api League and delegates rendering to weekly_recap.build_weekly_recap().
- weekly_recap handles logos, blurbs (Sabre), player call-outs, and awards insertion.
"""

import argparse
import os
import sys
import logging
from datetime import datetime
from typing import Optional, Dict, List

# Optional .env for local runs; in Actions, env comes from secrets
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

# Project module that actually renders the DOCX
try:
    import weekly_recap
except Exception as e:
    weekly_recap = None

LOG = logging.getLogger("build_gazette")


def _get_env(name: str) -> Optional[str]:
    v = os.getenv(name)
    if isinstance(v, str):
        v = v.strip()
    return v or None


def _resolve_cookies(cli_s2: Optional[str], cli_swid: Optional[str]) -> Dict[str, str]:
    """
    Priority: CLI > ENV (ESPN_S2/S2, ESPN_SWID/SWID).  We never print the values.
    """
    s2 = cli_s2 or _get_env("ESPN_S2") or _get_env("S2")
    swid = cli_swid or _get_env("ESPN_SWID") or _get_env("SWID")

    def _safe_len(v: Optional[str]) -> str:
        return f"present (len={len(v)})" if v else "missing"

    print(f"[env] ESPN_S2:{_safe_len(_get_env('ESPN_S2'))}  S2:{_safe_len(_get_env('S2'))}")
    print(f"[env] ESPN_SWID:{_safe_len(_get_env('ESPN_SWID'))}  SWID:{_safe_len(_get_env('SWID'))}")
    print(f"[cli] --s2:{_safe_len(cli_s2)}  --swid:{_safe_len(cli_swid)}")

    if not s2 or not swid:
        raise RuntimeError(
            "❌ Missing ESPN cookies. Provide --s2/--swid, or set ESPN_S2/ESPN_SWID in the environment.\n"
            "Without them, player stats, logos, awards, and blurbs cannot be generated."
        )
    if "{" not in swid or "}" not in swid:
        LOG.warning("⚠️ ESPN_SWID usually includes braces, e.g. {XXXXXXXX-XXXX-...}")

    return {"s2": s2, "swid": swid}


def _ensure_player_access(league: "League", week: int) -> None:
    """
    Quick sanity check: can we access starters? If not, cookies aren't really working.
    """
    try:
        board = league.scoreboard(week)
        if not board:
            LOG.warning("No matchups returned for week=%s. Continuing.", week)
            return
        m0 = board[0]
        starters = getattr(getattr(m0, "home_team", None), "starters", None)
        if starters is None:
            raise RuntimeError("No starters returned; cookies may be invalid or not passed to the process.")
    except Exception as e:
        raise RuntimeError("❌ Could not access player-level data (box scores/starters). Check cookies.") from e


def _parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build the Gridiron Gazette recap document.")
    p.add_argument("--league", type=int, default=int(_get_env("LEAGUE_ID") or 887998), help="ESPN League ID")
    p.add_argument("--year", type=int, default=int(_get_env("YEAR") or datetime.now().year), help="Season year")
    p.add_argument("--week", type=int, default=int(_get_env("WEEK") or 0), help="Week number; 0 = auto by ISO-approx")
    p.add_argument("--auto-week", action="store_true", help="Infer current week if --week=0")
    p.add_argument("--week-offset", type=int, default=0, help="Offset to add to inferred week")

    # Cookies via CLI (avoids local .env)
    p.add_argument("--s2", type=str, default=None, help="ESPN S2 cookie (espn_s2)")
    p.add_argument("--swid", type=str, default=None, help="ESPN SWID cookie (with braces)")

    p.add_argument("--template", type=str, default=_get_env("TEMPLATE") or _get_env("GAZETTE_TEMPLATE") or "recap_template.docx",
                   help="Path to recap_template.docx")
    p.add_argument("--output-dir", type=str, default=_get_env("OUTDOCX_DIR") or _get_env("GAZETTE_OUTDIR") or "recaps",
                   help="Output directory")

    # Blurbs
    p.add_argument("--llm-blurbs", action="store_true", help="Generate LLM blurbs (Sabre)")
    p.add_argument("--blurb-style", default=_get_env("BLURB_STYLE") or "sabre", help="Blurb voice/style key")
    p.add_argument("--blurb-words", type=int, default=int(_get_env("BLURB_WORDS") or 200), help="Approx words per blurb")

    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    return p.parse_args(argv)


def _infer_week(auto_week: bool, week: int, offset: int) -> int:
    if week and week > 0 and not auto_week:
        return week
    base = datetime.now().isocalendar().week % 18
    base = base or 1
    w = max(1, base + (offset or 0))
    return min(18, w)


def main(argv: Optional[List[str]] = None) -> int:
    if weekly_recap is None or not hasattr(weekly_recap, "build_weekly_recap"):
        raise RuntimeError("weekly_recap.build_weekly_recap not found in your repo.")

    args = _parse_args(argv or sys.argv[1:])
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s: %(message)s")

    cookies = _resolve_cookies(args.s2, args.swid)

    # espn_api League instance (lets storymaker compute blurbs from starters, etc.)
    league = League(league_id=args.league, year=args.year, espn_s2=cookies["s2"], swid=cookies["swid"])

    week = _infer_week(args.auto_week or args.week == 0, args.week, args.week_offset)
    LOG.info("Using week=%s", week)

    _ensure_player_access(league, week)

    outdoc = weekly_recap.build_weekly_recap(
        league=league,
        league_id=args.league,
        year=args.year,
        week=week,
        template=args.template,
        output_dir=args.output_dir,
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
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)
    except Exception as e:
        LOG.exception("Unhandled error: %s", e)
        raise SystemExit(2)
