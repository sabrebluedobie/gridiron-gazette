# gazette_helpers.py
from __future__ import annotations
from pathlib import Path
from typing import Optional

import logo_resolver as _logos

def find_logo_for(team_name: str) -> Optional[str]:
    return _logos.team_logo(team_name)

def find_league_logo(league_name: str) -> Optional[str]:
    return _logos.league_logo(league_name)

def find_sponsor_logo(sponsor_name: str) -> Optional[str]:
    return _logos.sponsor_logo(sponsor_name)
