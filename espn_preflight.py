# espn_preflight.py
from __future__ import annotations
import os, sys
from typing import Optional

def safe(v: Optional[str]) -> str:
    return "missing" if not v else f"present(len={len(v)})"

def die(msg: str, code: int = 1):
    print(f"❌ {msg}")
    sys.exit(code)

def main():
    print("🔎 ESPN/Env Preflight")

    s2   = os.getenv("ESPN_S2")
    swid = os.getenv("SWID") or os.getenv("ESPN_SWID")  # accept either name
    lid  = os.getenv("LEAGUE_ID")
    year = os.getenv("YEAR")
    logos= os.getenv("TEAM_LOGOS_FILE")

    print("ESPN_S2:", safe(s2))
    print("SWID   :", safe(swid))
    print("LEAGUE_ID:", lid)
    print("YEAR     :", year)
    print("TEAM_LOGOS_FILE:", logos)

    # Hard fail if cookies missing
    if not s2 or not swid:
        die("Cookies missing. Set repository secrets ESPN_S2 and SWID (SWID must include braces).")

    # Validate league vars
    if not lid or not lid.isdigit() or int(lid) <= 0:
        die("LEAGUE_ID not set or invalid. Set Actions → Variables → LEAGUE_ID (e.g., 887998).")
    if not year or not year.isdigit():
        die("YEAR not set or invalid. Set Actions → Variables → YEAR (e.g., 2025).")

    # Try ESPN API call
    try:
        from espn_api.football import League
        league = League(league_id=int(lid), year=int(year), espn_s2=s2, swid=swid)
        print(f"✅ Connected to league: {getattr(league, 'league_name', 'Unknown')}")
        print(f"Teams detected: {len(getattr(league, 'teams', []))}")
        # Light scoreboard probe (current week if available)
        try:
            week = int(os.getenv("WEEK_INPUT") or 0) or getattr(league, "currentMatchupPeriod", 1)
            _ = league.scoreboard(week=week)
            print(f"✅ Scoreboard ok for week {week}")
        except Exception as e:
            print(f"⚠️  Scoreboard probe warning: {e!r}")
    except Exception as e:
        die(f"ESPN API connection failed: {e!r}")

    print("✅ Preflight passed.")

if __name__ == "__main__":
    main()
