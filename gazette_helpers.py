# gazette_helpers.py

from docxtpl import DocxTemplate
from typing import Dict, Any, List

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
