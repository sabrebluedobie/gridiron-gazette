#!/usr/bin/env python3
"""
weekly_recap_multi.py — Run multiple leagues from config file
Updated to support Sabre-style LLM blurbs
"""
import argparse
import sys
import subprocess
import shlex
import time
import datetime as dt
import json
from pathlib import Path
import yaml

def parse_args():
    p = argparse.ArgumentParser(description="Build gazettes for multiple leagues")
    p.add_argument("--config", default="leagues.yml", help="Config file (YAML or JSON)")
    
    # Week selection
    p.add_argument("--week", type=int, help="Specific week number")
    p.add_argument("--auto-week", action="store_true", help="Auto-detect week")
    p.add_argument("--week-offset", type=int, default=0, help="Week offset")
    
    # LLM options
    p.add_argument("--llm-blurbs", action="store_true", help="Generate LLM blurbs")
    p.add_argument("--blurb-style", default="sabre", help="Blurb style (sabre/mascot/default)")
    p.add_argument("--blurb-words", type=int, default=300, help="Words per blurb")
    
    # Output
    p.add_argument("--output-dir", default="recaps", help="Output directory")
    p.add_argument("--stop-on-fail", action="store_true", help="Stop on first failure")
    p.add_argument("--verbose", action="store_true", help="Verbose output")
    
    return p.parse_args()

def compute_auto_week(offset=0) -> int:
    """Compute current week number"""
    today = dt.date.today()
    wk = int(today.strftime("%U"))
    return max(1, wk + offset)

def load_config(config_path: str):
    """Load league configuration from YAML or JSON"""
    path = Path(config_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    content = path.read_text(encoding="utf-8")
    
    # Try YAML first
    if config_path.endswith(('.yml', '.yaml')):
        data = yaml.safe_load(content)
    else:
        # Try JSON
        data = json.loads(content)
    
    # Handle different formats
    if isinstance(data, dict) and "leagues" in data:
        return data["leagues"]
    elif isinstance(data, list):
        return data
    else:
        raise ValueError(f"Invalid config format in {config_path}")

def run_one_league(league_id, year, week, args):
    """Build gazette for a single league"""
    cmd = [
        sys.executable, "build_gazette.py",
        "--league-id", str(league_id),
        "--year", str(year),
        "--week", str(week),
        "--output-dir", args.output_dir,
    ]
    
    # Add LLM options if enabled
    if args.llm_blurbs:
        cmd.extend([
            "--llm-blurbs",
            "--blurb-style", args.blurb_style,
            "--blurb-words", str(args.blurb_words),
        ])
    
    if args.verbose:
        cmd.append("--verbose")
        print(f"[multi] Command: {' '.join(shlex.quote(c) for c in cmd)}")
    
    return subprocess.run(cmd).returncode

def main():
    args = parse_args()
    
    # Load configuration
    try:
        leagues = load_config(args.config)
    except Exception as e:
        print(f"[ERROR] Failed to load config: {e}")
        sys.exit(2)
    
    if not leagues:
        print(f"[ERROR] No leagues found in {args.config}")
        sys.exit(2)
    
    # Determine week
    week = args.week if args.week is not None else compute_auto_week(args.week_offset)
    
    print(f"=== Multi-League Gazette Builder ===")
    print(f"Config: {args.config}")
    print(f"Leagues: {len(leagues)}")
    print(f"Week: {week}")
    print(f"LLM Blurbs: {args.llm_blurbs}")
    if args.llm_blurbs:
        print(f"Blurb Style: {args.blurb_style}")
    print()
    
    # Process each league
    failures = []
    successes = []
    
    for i, league_cfg in enumerate(leagues, 1):
        # Handle different config formats
        if isinstance(league_cfg, dict):
            name = league_cfg.get("name", f"League {i}")
            league_id = league_cfg.get("id") or league_cfg.get("league_id")
            year = league_cfg.get("year")
        else:
            print(f"[WARN] Skipping invalid league config: {league_cfg}")
            continue
        
        if not league_id or not year:
            print(f"[WARN] Skipping {name}: missing id or year")
            continue
        
        print(f"[{i}/{len(leagues)}] Building {name} (id={league_id})...")
        
        t0 = time.time()
        rc = run_one_league(league_id, year, week, args)
        dt_s = time.time() - t0
        
        if rc == 0:
            print(f"  ✅ SUCCESS in {dt_s:.1f}s")
            successes.append(name)
        else:
            print(f"  ❌ FAILED (rc={rc})")
            failures.append({"name": name, "id": league_id, "rc": rc})
            
            if args.stop_on_fail:
                print("[multi] Stopping due to failure (--stop-on-fail)")
                break
    
    # Summary
    print(f"\n=== Summary ===")
    print(f"Successes: {len(successes)}")
    print(f"Failures: {len(failures)}")
    
    if successes:
        print(f"\n✅ Successful leagues:")
        for name in successes:
            print(f"  - {name}")
    
    if failures:
        print(f"\n❌ Failed leagues:")
        for f in failures:
            print(f"  - {f['name']} (id={f['id']}, rc={f['rc']})")
    
    sys.exit(1 if failures else 0)

if __name__ == "__main__":
    main()