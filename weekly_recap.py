#!/usr/bin/env python3
# weekly_recap.py — thin, safe orchestrator around build_gazette.py
import argparse, sys, subprocess, shlex, time, datetime as dt

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--league-id", required=True)
    p.add_argument("--year", type=int, required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--week", type=int)
    g.add_argument("--auto-week", action="store_true")
    p.add_argument("--week-offset", type=int, default=0)
    p.add_argument("--llm-blurbs", action="store_true")
    p.add_argument("--output-dir", default="recaps")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()

def compute_auto_week(offset=0) -> int:
    # Simple placeholder; adjust later if you want true NFL-week logic
    today = dt.date.today()
    wk = int(today.strftime("%U"))
    return max(1, wk + offset)

def run_build(args):
    week = args.week if args.week is not None else compute_auto_week(args.week_offset)
    if args.dry_run:
        print(f"[weekly_recap] DRY RUN league={args.league_id} year={args.year} week={week}")
        return 0

    cmd = [
        sys.executable, "build_gazette.py",
        "--league-id", str(args.league_id),
        "--year", str(args.year),
        "--week", str(week),
        "--output-dir", args.output_dir,
    ]
    if args.llm_blurbs: cmd.append("--llm-blurbs")

    if args.verbose:
        print("[weekly_recap] ", " ".join(shlex.quote(c) for c in cmd))

    t0 = time.time()
    rc = subprocess.run(cmd).returncode
    dt_s = time.time() - t0
    print(f"[weekly_recap] {'SUCCESS' if rc==0 else 'FAILED'} in {dt_s:.1f}s (week={week})")
    return rc

def main():
    args = parse_args()
    sys.exit(run_build(args))

if __name__ == "__main__":
    main()
