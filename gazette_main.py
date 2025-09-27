#!/usr/bin/env python3
from __future__ import annotations
"""
gazette_main.py
---------------
Project entrypoint that delegates to build_gazette’s CLI.
This keeps your historical CLI flags working, while using the
new weekly_recap pipeline that fills MATCHUP{i}_BLURB with
Sabre’s 200–250 word recaps (plus 🐾 signoff) and renders the DOCX.
"""
import sys
import logging

from build_gazette import main as build_main

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

if __name__ == "__main__":
    # Pass through all CLI args (e.g., --league-id/--year/--week/--llm-blurbs)
    build_main(sys.argv[1:])
