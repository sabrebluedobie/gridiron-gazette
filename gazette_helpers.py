# gazette_helpers.py

from docxtpl import DocxTemplate
from typing import Dict, Any, List
# gazette_helpers.py
import json, re
from pathlib import Path

BASE_DIR = Path(".")                        # project root
LOGO_DIR = BASE_DIR / "logos" / "team_logos"

def _slug(s: str) -> str:
    s = s.lower().replace("’", "'")         # normalize curly apostrophe
    s = s.replace("'", "")                  # drop apostrophes
    s = re.sub(r"\s+", "_", s)              # spaces -> underscore
    s = re.sub(r"[^a-z0-9_]", "", s)        # strip emoji/punct
    return s

def find_logo_for(team_name: str) -> str:
    """Return a root-relative path to a team logo; never 'logos/logos/...'.
       Falls back to default if not found."""
    map_path = BASE_DIR / "team_logos.json"
    mapping = {}
    if map_path.exists():
        mapping = json.loads(map_path.read_text(encoding="utf-8"))

    # 1) Direct mapping lookup (root-relative path like 'logos/team_logos/...').
    rel = mapping.get(team_name)
    if rel:
        p = BASE_DIR / rel
        if p.exists():
            return str(p.as_posix())

    # 2) Try slugged-key match (if incoming name differs in punctuation/case).
    slug = _slug(team_name)
    for k, v in mapping.items():
        if _slug(k) == slug:
            p = BASE_DIR / v
            if p.exists():
                return str(p.as_posix())

    # 3) Scan the logo folder for a filename whose slug matches.
    for p in LOGO_DIR.glob("*.*"):
        if _slug(p.stem) == slug:
            return str(p.as_posix())

    # 4) Default
    fallback = LOGO_DIR / "_default.png"
    print(f"[WARN] Logo not found for {team_name}; using default: {fallback}")
    return str(fallback.as_posix())

# ---------- Context mapping helpers ----------
def add_enumerated_matchups(context: Dict[str, Any], max_slots: int) -> None:
    """
    Expand context['games'] list into numbered keys the template uses:
    MATCHUPi_HOME, _AWAY, _HS, _AS, _BLURB, spotlight stats, plus legacy TEAMS/HEADLINE/BODY.
    """
    games: List[Dict[str, Any]] = context.get("games", []) or []
    for i in range(1, max_slots + 1):
        g = games[i - 1] if i - 1 < len(games) else {}

        home = g.get("home", "") or ""
        away = g.get("away", "") or ""
        hs = g.get("hs", "")
        aS = g.get("as", "")  # 'as' is a keyword; we keep the dict key but store as aS var

        blurb = g.get("blurb", "") or ""
        top_home = g.get("top_home", "") or ""
        top_away = g.get("top_away", "") or ""
        bust = g.get("bust", "") or ""
        keyplay = g.get("keyplay", "") or ""
        dnote = g.get("def", "") or ""

        context[f"MATCHUP{i}_HOME"] = home
        context[f"MATCHUP{i}_AWAY"] = away
        context[f"MATCHUP{i}_HS"] = hs
        context[f"MATCHUP{i}_AS"] = aS
        context[f"MATCHUP{i}_BLURB"] = blurb

        context[f"MATCHUP{i}_TOP_HOME"] = top_home
        context[f"MATCHUP{i}_TOP_AWAY"] = top_away
        context[f"MATCHUP{i}_BUST"] = bust
        context[f"MATCHUP{i}_KEYPLAY"] = keyplay
        context[f"MATCHUP{i}_DEF"] = dnote

        # Legacy/compatibility fields
        try:
            hs_f = float(hs) if hs != "" else float("nan")
            as_f = float(aS) if aS != "" else float("nan")
            if hs != "" and aS != "":
                scoreline = f"{home} {hs} – {away} {aS}"
            else:
                scoreline = f"{home} vs {away}".strip()
            headline = f"{home if hs_f >= as_f else away} def. {away if hs_f >= as_f else home}"
        except Exception:
            scoreline = f"{home} vs {away}".strip()
            headline = scoreline

        context[f"MATCHUP{i}_TEAMS"] = scoreline
        context[f"MATCHUP{i}_HEADLINE"] = headline
        context[f"MATCHUP{i}_BODY"] = blurb


def add_template_synonyms(context: Dict[str, Any], slots: int) -> None:
    """
    Flatten award structures and add top-level aliases your Word template uses.
    """
    context["WEEK_NUMBER"] = context.get("week", "")
    if "WEEKLY_INTRO" not in context:
        context["WEEKLY_INTRO"] = context.get("intro", "")

    awards = context.get("awards", {}) or {}
    top_score = awards.get("top_score", {}) or {}
    low_score = awards.get("low_score", {}) or {}
    largest_gap = awards.get("largest_gap", {}) or {}

    context["AWARD_TOP_TEAM"] = top_score.get("team", "")
    context["AWARD_TOP_NOTE"] = str(top_score.get("points", "")) or ""
    context["AWARD_CUPCAKE_TEAM"] = low_score.get("team", "")
    context["AWARD_CUPCAKE_NOTE"] = str(low_score.get("points", "")) or ""
    context["AWARD_KITTY_TEAM"] = largest_gap.get("desc", "")
    context["AWARD_KITTY_NOTE"] = str(largest_gap.get("gap", "")) or ""

def _find_from_map(name: str, map_file: str, folder: Path, default_name: str) -> str:
    """Generic logo lookup by display name, then slug, then filename scan."""
    mapping = {}
    mp = BASE_DIR / map_file
    if mp.exists():
        mapping = json.loads(mp.read_text(encoding="utf-8"))

    # 1) direct
    rel = mapping.get(name)
    if rel and (BASE_DIR/rel).exists():
        return str((BASE_DIR/rel).as_posix())

    # 2) slugged key match
    want = _slug(name)
    for k, v in mapping.items():
        if _slug(k) == want and (BASE_DIR/v).exists():
            return str((BASE_DIR/v).as_posix())

    # 3) scan folder for slugged filename
    for p in folder.glob("*.*"):
        if _slug(p.stem) == want:
            return str(p.as_posix())

    # 4) default
    fallback = folder / default_name
    print(f"[WARN] Logo not found for {name}; using default: {fallback}")
    return str(fallback.as_posix())

def find_league_logo(league_name: str) -> str:
    return _find_from_map(
        league_name,
        "league_logos.json",
        BASE_DIR / "logos" / "league_logos",
        "_default.png"
    )

def find_sponsor_logo(sponsor_name: str) -> str:
    return _find_from_map(
        sponsor_name,
        "sponsor_logos.json",
        BASE_DIR / "logos" / "sponsor_logos",
        "_default.png"
    )
# --- end add ---


