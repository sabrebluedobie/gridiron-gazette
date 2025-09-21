#!/usr/bin/env python3
# weekly_recap_multi.py — run multiple leagues from leagues.yml
import argparse, sys, subprocess, shlex, time, datetime as dt, json
from pathlib import Path
import yaml  # pip install pyyaml

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="leagues.yml")
    p.add_argument("--week", type=int)
    p.add_argument("--auto-week", action="store_true")
    p.add_argument("--week-offset", type=int, default=0)
    p.add_argument("--llm-blurbs", action="store_true")
    p.add_argument("--output-dir", default="recaps")
    p.add_argument("--stop-on-fail", action="store_true")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()

def compute_auto_week(offset=0) -> int:
    today = dt.date.today()
    wk = int(today.strftime("%U"))
    return max(1, wk + offset)

def run_one(league_id, year, week, llm, outdir, verbose):
    cmd = [sys.executable, "build_gazette.py",
           "--league-id", str(league_id), "--year", str(year), "--week", str(week),
           "--output-dir", outdir]
    if llm: cmd.append("--llm-blurbs")
    if verbose: print("[multi] ", " ".join(shlex.quote(c) for c in cmd))
    return subprocess.run(cmd).returncode

def main():
    args = parse_args()
    data = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    leagues = data.get("leagues", [])
    if not leagues:
        print("[multi] No leagues found in config.")
        sys.exit(2)

    week = args.week if args.week is not None else compute_auto_week(args.week_offset)
    print(f"[multi] Running {len(leagues)} league(s) for week={week}")

    failures = []
    for row in leagues:
        name = row.get("name", "?")
        lid  = row["id"]; year = row["year"]
        rc = run_one(lid, year, week, args.llm_blurbs, args.output_dir, args.verbose)
        if rc != 0:
            failures.append({"name": name, "id": lid, "rc": rc})
            print(f"[multi] FAIL: {name} (id={lid}) rc={rc}")
            if args.stop_on_fail:
                print("[multi] stop-on-fail enabled; aborting.")
                break
        else:
            print(f"[multi] OK: {name} (id={lid})")

    print(f"[multi] Done. Failures: {json.dumps(failures, indent=2)}")
    sys.exit(1 if failures else 0)

if __name__ == "__main__":
    main()
