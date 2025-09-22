#!/usr/bin/env python3
"""
build_gazette.py — patched

Key changes:
- Fail fast if ESPN cookies (ESPN_S2 / ESPN_SWID) are missing.
- Loads .env automatically for local runs (keeps GH Actions compatible).
- Clear logging and CLI flags.
- Basic sanity check to ensure player-level data is available (not just team scores).
"""

import argparse
import os
import sys
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

# Load .env when running locally. In GitHub Actions, env comes from secrets.
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

# ESPN
try:
    from espn_api.football import League  # type: ignore
except Exception as e:
    print("❌ Missing dependency: espn_api. Run `pip install espn-api`.", file=sys.stderr)
    raise

# Optional modules from your repo (safe imports; we guard AttributeError below)
try:
    import weekly_recap  # your module that renders the DOCX/PDF
except Exception:
    weekly_recap = None  # we'll error nicely if it's required

try:
    import storymaker  # your module that generates blurbs via LLM
except Exception:
    storymaker = None

LOG = logging.getLogger("build_gazette")


def get_env(name: str, fallback: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name, fallback)
    if v is not None and isinstance(v, str):
        v = v.strip()
    return v or None


def require_cookies() -> Dict[str, str]:
    """
    Read ESPN cookies from env and fail fast if they are missing.
    Accepts both ESPN_S2/S2 and ESPN_SWID/SWID for convenience.
    """
    s2 = get_env("ESPN_S2") or get_env("S2")
    swid = get_env("ESPN_SWID") or get_env("SWID")

    if not s2 or not swid:
        raise RuntimeError(
            "❌ Missing ESPN cookies. Set ESPN_S2 and ESPN_SWID "
            "(or S2 / SWID) in your environment or .env.\n"
            "Without them, player stats, awards, logos, and blurbs cannot be generated."
        )

    # Basic shape check for SWID: must include surrounding braces
    if "{" not in swid or "}" not in swid:
        LOG.warning("⚠️ ESPN_SWID usually includes braces, e.g. {XXXXXXXX-XXXX-...}. Yours doesn't appear to.")

    return {"s2": s2, "swid": swid}


def infer_week(auto_week: bool, week: Optional[int], week_offset: int) -> int:
    if week and week > 0:
        return week
    if auto_week:
        # Default to ESPN-style current week; add offset (+/-)
        today = datetime.utcnow().date()
        # Conservative guess: by default use ISO week number mod 18 (approx NFL reg season length)
        base = (int(today.strftime("%V")) % 18) or 1
        return max(1, base + week_offset)
    # Fallback
    return max(1, (datetime.utcnow().isocalendar().week % 18) + week_offset)


def ensure_player_data(league: "League", week: int) -> None:
    """
    Sanity check: try to access player-level data so we know cookies actually work.
    If we can access starters or box scores for at least one team, we assume we're good.
    """
    try:
        matchups = getattr(league, "scoreboard", lambda w: [])(week)
        if not matchups:
            LOG.warning("No matchups returned for week %s. Continuing, but output may be empty.", week)
            return

        # Look at first matchup's home team roster/starter points.
        m0 = matchups[0]
        home = getattr(m0, "home_team", None)
        if not home:
            LOG.warning("Matchup object without home_team; continuing.")
            return

        starters = getattr(home, "starters", None)
        if starters is None:
            raise RuntimeError("ESPN returned no starters list (likely cookie issue).")

        # Access at least one player's points if available
        if starters:
            _ = getattr(starters[0], "points", None)
        else:
            LOG.warning("Starters list is empty; proceeding anyway.")

    except Exception as e:
        raise RuntimeError(
            "❌ Could not access player-level data from ESPN. "
            "Cookies may be invalid/expired or not passed to the process."
        ) from e


def build_doc(league: "League", year: int, week: int, template: Optional[str], outdir: str, verbose: bool) -> str:
    if weekly_recap is None or not hasattr(weekly_recap, "build_weekly_recap"):
        raise RuntimeError("weekly_recap.build_weekly_recap not found. Ensure your repo has weekly_recap.py with that function.")

    kwargs = {"league": league, "year": year, "week": week}
    if template:
        kwargs["template"] = template
    if outdir:
        kwargs["output_dir"] = outdir

    if verbose:
        LOG.info("Calling weekly_recap.build_weekly_recap with %s", kwargs)

    # Expecting function to return output DOCX path
    return weekly_recap.build_weekly_recap(**kwargs)  # type: ignore[arg-type]


def maybe_make_blurbs(league: "League", year: int, week: int, style: str, words: int, enabled: bool) -> List[str]:
    if not enabled:
        return []
    if storymaker is None or not hasattr(storymaker, "generate_blurbs"):
        raise RuntimeError("storymaker.generate_blurbs not found. Ensure your repo has storymaker.py with that function.")

    api_key = get_env("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("❌ OPENAI_API_KEY is required when --llm-blurbs is set.")
    os.environ["OPENAI_API_KEY"] = api_key  # ensure submodules can see it

    return storymaker.generate_blurbs(league, year=year, week=week, style=style, max_words=words)  # type: ignore


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build the Gridiron Gazette recap document.")
    p.add_argument("--league", type=int, default=int(get_env("LEAGUE_ID") or 887998), help="ESPN League ID")
    p.add_argument("--year", type=int, default=int(get_env("YEAR") or datetime.utcnow().year), help="Season year")
    p.add_argument("--week", type=int, default=int(get_env("WEEK") or 0), help="Scoring week (1..18). 0 means auto")
    p.add_argument("--auto-week", action="store_true", help="Infer current week if --week is 0")
    p.add_argument("--week-offset", type=int, default=0, help="Offset to add to inferred week")

    p.add_argument("--template", type=str, default=get_env("GAZETTE_TEMPLATE") or "", help="Path to recap_template.docx")
    p.add_argument("--output-dir", type=str, default=get_env("GAZETTE_OUTDIR") or "recaps", help="Output directory")

    # Blurbs
    p.add_argument("--llm-blurbs", action="store_true", help="Generate LLM blurbs")
    p.add_argument("--blurb-style", default=get_env("BLURB_STYLE") or "sabre", help="Blurb tone/style")
    p.add_argument("--blurb-words", type=int, default=int(get_env("BLURB_WORDS") or 300), help="Approx words per blurb")

    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    cookies = require_cookies()
    league = League(league_id=args.league, year=args.year, espn_s2=cookies["s2"], swid=cookies["swid"])

    # Determine week
    week = infer_week(args.auto_week or args.week == 0, args.week, args.week_offset)
    LOG.info("Using week=%s", week)

    # Ensure we truly have player-level data (not just public scores)
    ensure_player_data(league, week)

    # Build document
    outdoc = build_doc(league, args.year, week, args.template or None, args.output_dir, args.verbose)
    print(f"✅ Recap generated: {outdoc}")

    # Optional blurbs
    if args.llm_blurbs:
        blurbs = maybe_make_blurbs(league, args.year, week, args.blurb_style, args.blurb_words, enabled=True)
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
