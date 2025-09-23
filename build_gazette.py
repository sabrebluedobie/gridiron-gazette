#!/usr/bin/env python3
import os
import sys
import logging
from datetime import datetime
from pathlib import Path
import argparse

# ✨ NEW: load .env so local runs pick up ESPN_S2 / SWID / TEAM_LOGOS_FILE, etc.
try:
    from dotenv import load_dotenv  # python-dotenv
    load_dotenv()
except Exception:
    pass

import weekly_recap as weekly_recap  # or: import weekly_recap
# If you kept the file name `weekly_recap.py`, use: import weekly_recap

log = logging.getLogger("build_gazette")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")


def get_env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if (v and str(v).strip()) else default


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser("Gridiron Gazette builder")
    p.add_argument("--league", "--league-id", dest="league_id",
                   type=int, default=int(get_env("LEAGUE_ID") or 0),
                   help="ESPN League ID (or set LEAGUE_ID env)")
    # Keep utcnow for compatibility; your warning is harmless.
    p.add_argument("--year", type=int,
                   default=int(get_env("YEAR") or datetime.utcnow().year),
                   help="Season year (or set YEAR env)")
    p.add_argument("--week", type=int, default=None, help="Week number")

    p.add_argument("--template", default=get_env("TEMPLATE") or "recap_template.docx",
                   help="Path to .docx template (or TEMPLATE env)")
    p.add_argument("--outdocx", default=get_env("OUTDOCX") or "recaps/Week{week}_Gazette.docx",
                   help="Output file or directory (supports tokens {week},{week02},{year},{league})")

    # ✨ NEW: Make Sabre blurbs the default, always on, unless explicitly disabled
    p.add_argument("--llm-blurbs", dest="llm_blurbs", action="store_true",
                   default=True, help="Generate Sabre blurbs (default ON)")
    p.add_argument("--no-blurbs", dest="llm_blurbs", action="store_false",
                   help="Disable LLM blurbs")
    p.add_argument("--blurb-style", default=get_env("BLURB_STYLE") or "sabre",
                   choices=["sabre", "neutral", "hype"],
                   help="Blurb voice/style (default: sabre)")
    p.add_argument("--blurb-words", type=int, default=int(get_env("BLURB_WORDS") or 200),
                   help="Target words per blurb (default: 200)")

    p.add_argument("--verbose", action="store_true", default=("true" == str(get_env("VERBOSE","")).lower()))
    return p.parse_args()


def main():
    args = parse_args()

    if args.verbose:
        log.setLevel(logging.INFO)
        log.info("[env] ESPN_S2:%s  SWID:%s",
                 "present" if os.getenv("ESPN_S2") or os.getenv("S2") else "missing",
                 "present" if os.getenv("SWID") or os.getenv("ESPN_SWID") else "missing")
        log.info("[env] TEAM_LOGOS_FILE=%s", os.getenv("TEAM_LOGOS_FILE"))
        log.info("Using week=%s", args.week)

    # Optional heads-up if blurbs requested but no API key
    if args.llm_blurbs and not os.getenv("OPENAI_API_KEY"):
        log.warning("OPENAI_API_KEY not set; Sabre blurbs may be skipped or use fallback.")

    # Create ESPN League lazily inside the recap (gazette_data handles cookie names)
    out = weekly_recap.build_weekly_recap(
        league=None,                      # weekly_recap/gazette_data will construct as needed
        league_id=int(args.league_id),
        year=int(args.year),
        week=int(args.week) if args.week is not None else 0,
        template=args.template,
        output_dir=args.outdocx,
        llm_blurbs=bool(args.llm_blurbs),     # 🔒 Sabre ON by default
        blurb_style=str(args.blurb_style),    # 🔒 default 'sabre'
        blurb_words=int(args.blurb_words),
    )
    print(f"✅ Recap generated: {out}")
    print("🎉 Build complete.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
