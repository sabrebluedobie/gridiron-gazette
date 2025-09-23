#!/usr/bin/env python3
"""
build_gazette.py — Gridiron Gazette runner (YAML-aware, fail-fast, template-ready)

What’s new in this edition
- **gazette.yml support** (optional): place a `gazette.yml` at repo root to set
  defaults like league_id, year, template, output_dir, blurb style, etc.
- **Precedence**: CLI > ENV > gazette.yml > built-ins.
- Still fails fast on missing ESPN cookies; still supports `--s2/--swid` CLI.
- Hands off to weekly_recap.build_weekly_recap(...) to render the DOCX.

Install (local):
  pip install espn-api docxtpl python-dotenv pyyaml openai requests
"""

import argparse
import os
import sys
import logging
from datetime import datetime
from typing import Optional, Dict, List
from pathlib import Path

# Optional .env for local runs; in Actions, env comes from secrets
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

# Optional YAML config
_YAML = None
try:
    import yaml  # type: ignore
    _YAML = yaml
except Exception:
    _YAML = None

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


# ------------- config helpers -------------

def _load_yaml_defaults(path: str = "gazette.yml") -> Dict[str, object]:
    if not _YAML:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = _YAML.safe_load(p.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            return {}
        # normalize keys to snake_case used below
        norm = {str(k).strip().lower(): v for k, v in data.items()}
        return norm
    except Exception as e:
        print(f"⚠️ Could not read {path}: {e}", file=sys.stderr)
        return {}


def _env(name: str) -> Optional[str]:
    v = os.getenv(name)
    if isinstance(v, str):
        v = v.strip()
    return v or None


def _resolve_default(cfg: Dict[str, object], env_name: str, cfg_key: str, fallback: object) -> object:
    # Precedence: ENV > YAML > fallback
    return _env(env_name) or cfg.get(cfg_key, fallback)


def _resolve_cookies(cli_s2: Optional[str], cli_swid: Optional[str]) -> Dict[str, str]:
    """
    Priority: CLI > ENV (ESPN_S2/S2, ESPN_SWID/SWID).  We never print the values.
    """
    s2 = cli_s2 or _env("ESPN_S2") or _env("S2")
    swid = cli_swid or _env("ESPN_SWID") or _env("SWID")

    def _safe_len(v: Optional[str]) -> str:
        return f"present (len={len(v)})" if v else "missing"

    print(f"[env] ESPN_S2:{_safe_len(_env('ESPN_S2'))}  S2:{_safe_len(_env('S2'))}")
    print(f"[env] ESPN_SWID:{_safe_len(_env('ESPN_SWID'))}  SWID:{_safe_len(_env('SWID'))}")
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


def _infer_week(auto_week: bool, week: int, offset: int) -> int:
    if week and week > 0 and not auto_week:
        return week
    base = datetime.now().isocalendar().week % 18
    base = base or 1
    w = max(1, base + (offset or 0))
    return min(18, w)


def _parse_args(argv: List[str]) -> argparse.Namespace:
    # Load YAML first so we can set parser defaults from it
    cfg = _load_yaml_defaults()

    def dflt(env_name: str, cfg_key: str, fallback: object) -> object:
        return _resolve_default(cfg, env_name, cfg_key, fallback)

    p = argparse.ArgumentParser(description="Build the Gridiron Gazette recap document.")

    # Core
    p.add_argument("--league", type=int, default=int(dflt("LEAGUE_ID", "league_id", 887998)), help="ESPN League ID")
    p.add_argument("--year", type=int, default=int(dflt("YEAR", "year", datetime.now().year)), help="Season year")
    p.add_argument("--week", type=int, default=int(dflt("WEEK", "week", 0)), help="Week number; 0 = auto by ISO-approx")
    p.add_argument("--auto-week", action="store_true", default=bool(cfg.get("auto_week", False)),
                   help="Infer current week if --week=0")
    p.add_argument("--week-offset", type=int, default=int(cfg.get("week_offset", 0)),
                   help="Offset to add to inferred week")

    # Cookies via CLI (avoid local .env if preferred)
    p.add_argument("--s2", type=str, default=None, help="ESPN S2 cookie (espn_s2)")
    p.add_argument("--swid", type=str, default=None, help="ESPN SWID cookie (with braces)")

    # Template / output
    p.add_argument("--template", type=str,
                   default=str(dflt("GAZETTE_TEMPLATE", "template", "recap_template.docx")),
                   help="Path to recap_template.docx")
    p.add_argument("--output-dir", type=str,
                   default=str(dflt("GAZETTE_OUTDIR", "output_dir", "recaps")),
                   help="Output directory")

    # Blurbs
    p.add_argument("--llm-blurbs", action="store_true",
                   default=bool(_env("LLM_BLURBS") or cfg.get("llm_blurbs", False)),
                   help="Generate LLM blurbs (Sabre)")
    p.add_argument("--blurb-style", default=str(dflt("BLURB_STYLE", "blurb_style", "sabre")),
                   help="Blurb voice/style key")
    p.add_argument("--blurb-words", type=int, default=int(dflt("BLURB_WORDS", "blurb_words", 200)),
                   help="Approx words per blurb")

    # Misc
    p.add_argument("--verbose", action="store_true",
                   default=bool(_env("VERBOSE") or cfg.get("verbose", False)),
                   help="Verbose logging")

    args = p.parse_args(argv)

    # If YAML defined a display name, expose it to downstream modules via env (unless already set)
    if cfg.get("league_display_name") and not _env("LEAGUE_DISPLAY_NAME"):
        os.environ["LEAGUE_DISPLAY_NAME"] = str(cfg["league_display_name"])

    return args


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
