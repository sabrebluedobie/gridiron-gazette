#!/usr/bin/env python3
from __future__ import annotations
import os
import sys
import argparse
import logging
from datetime import datetime
from pathlib import Path

# Optional .env for local runs; harmless in CI (secrets come from Actions env)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Our builder
import weekly_recap

log = logging.getLogger("build_gazette")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def _positive_int(name: str, val: int | None) -> int:
    if val is None or int(val) <= 0:
        raise argparse.ArgumentTypeError(f"{name} must be a positive integer")
    return int(val)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build a Gridiron Gazette DOCX for a single week.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--league-id",
                   type=int,
                   default=int(os.getenv("LEAGUE_ID", "0")),
                   help="ESPN League ID (or set LEAGUE_ID)")
    p.add_argument("--year",
                   type=int,
                   default=int(os.getenv("YEAR", datetime.now().year)),
                   help="Season year (or set YEAR)")
    p.add_argument("--week",
                   type=int,
                   default=None,
                   help="Week number; if omitted uses league.current_week")
    p.add_argument("--template",
                   default=os.getenv("TEMPLATE", "recap_template.docx"),
                   help="Path to the Word template")
    p.add_argument("--output",
                   default=os.getenv("OUTPUT", "recaps/Gazette_{year}_W{week02}.docx"),
                   help="Output path pattern; supports {year} {week} {week02}")
    llm = p.add_mutually_exclusive_group()
    llm.add_argument("--llm-blurbs", action="store_true",
                     help="Enable Sabre LLM recaps (200–250 words)")
    llm.add_argument("--no-llm", dest="llm_blurbs", action="store_false",
                     help="Disable LLM (use simple fallback blurbs)")
    p.set_defaults(llm_blurbs=bool(os.getenv("LLM_BLURBS", "1") != "0"))
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    p.add_argument("--debug", action="store_true", help="Print traceback on failure")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if args.verbose:
        log.setLevel(logging.DEBUG)

    if not args.league_id:
        log.error("Missing --league-id (or LEAGUE_ID).")
        sys.exit(2)
    if not args.year:
        log.error("Missing --year (or YEAR).")
        sys.exit(2)

    # Resolve template existence early
    tpl = Path(args.template)
    if not tpl.exists():
        log.error(f"Template not found: {tpl.resolve()}")
        sys.exit(2)

    # If week is omitted, weekly_recap will fetch league.current_week
    try:
        out_path = weekly_recap.build_weekly_recap(
            league_id=int(args.league_id),
            year=int(args.year),
            week=None if args.week is None else int(args.week),
            template=str(tpl),
            output_path=str(args.output),
            use_llm_blurbs=bool(args.llm_blurbs),
        )
        log.info(f"✅ Gazette built: {out_path}")
    except KeyboardInterrupt:
        log.error("❌ Build interrupted")
        sys.exit(130)
    except Exception as e:
        log.error(f"❌ Build failed: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
