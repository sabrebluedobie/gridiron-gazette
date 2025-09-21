#!/usr/bin/env python3
# weekly_recap.py — thin, safe orchestrator around build_gazette
import argparse, sys, logging, subprocess, shlex, datetime as dt, time

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--league-id", required=True)
    p.add_argument("--year", type=int, required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--week", type=int)
    g.add_argument("--auto-week", action="store_true")
    p.add_argument("--week-offset", type=int, default=0)  # for auto-week tweaks on Mon/Tue
    p.add_argument("--llm-blurbs", action="store_true")
    p.add_argument("--output-dir", default="recaps")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()

def compute_auto_week(offset=0) -> int:
    # Simple approach: last completed NFL week (customize later if needed)
    # Use ISO week math or an env var; for beta we’ll keep it explicit.
    # Placeholder: default to current week number (Sun-Sat) + offset
    today = dt.date.today()
    week_num = int(today.strftime("%U"))  # simple week-of-year; customize later
    return max(1, week_num + offset)

def run_build(league_id, year, week, llm, outdir, verbose, dry_run):
    cmd = [
        sys.executable, "build_gazette.py",
        "--league-id", str(league_id),
        "--year", str(year),
        "--week", str(week),
        "--output-dir", outdir,
    ]
    if llm: cmd.append("--llm-blurbs")
    if dry_run: cmd.append("--dry-run")
    if verbose: print("[orchestrator] ", " ".join(shlex.quote(c) for c in cmd))
    start = time.time()
    res = subprocess.run(cmd)
    sec = time.time() - start
    if res.returncode != 0:
        print(f"[weekly_recap] FAILED in {sec:.1f}s (week={week})")
        sys.exit(res.returncode)
    print(f"[weekly_recap] SUCCESS in {sec:.1f}s (week={week})")

def main():
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    try:
        week = args.week if args.week else compute_auto_week(args.week_offset)
        if args.dry_run:
            print(f"[weekly_recap] DRY RUN league={args.league_id} year={args.year} week={week}")
            sys.exit(0)
        run_build(args.league_id, args.year, week, args.llm_blurbs, args.output_dir, args.verbose, args.dry_run)
        sys.exit(0)
    except Exception as e:
        logging.exception("weekly_recap crashed: %s", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
