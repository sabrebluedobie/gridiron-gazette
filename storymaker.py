"""
storymaker.py — LLM blurb generator with Sabre voice routing.

- Loads Sabre voice prompt from prompts/sabre_voice.txt or ENV fallback.
- Builds structured matchup context from espn_api League object.
- Calls OpenAI (or returns a templated fallback if unavailable).
- Returns a list[str] of blurbs, one per matchup.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import List, Dict, Any

# Optional OpenAI import — we fail with a clear error if missing when used.
_OPENAI_IMPORTED = True
try:
    from openai import OpenAI  # new SDK
except Exception:
    try:
        import openai  # legacy
    except Exception:
        _OPENAI_IMPORTED = False


def load_sabre_prompt() -> str:
    # 1) ENV override
    env_text = os.getenv("GAZETTE_SABRE_PROMPT")
    if env_text and env_text.strip():
        return env_text.strip()

    # 2) prompts file
    for p in (Path("prompts") / "sabre_voice.txt", Path("config") / "sabre_voice.txt"):
        if p.exists():
            try:
                return p.read_text(encoding="utf-8").strip()
            except Exception:
                pass

    # 3) safe default
    return (
        "You are Sabre, the Gridiron Gazette’s blue/grey Doberman mascot and beat reporter. "
        "Voice: hard-working, witty, light snark, family-friendly. Speak in first person as Sabre. "
        "Rules: Do not invent stats; only use provided data. No mascots/nicknames from leagues; use team names only. "
        "Always call out the key swing play, top scorers, any underperformers vs projection, and a decisive lineup choice if present. "
        "Aim ~200 words. End with ‘Sabre out—see you in Week {week}.’"
    )


def normalize_name(name: str) -> str:
    # Remove most emoji/symbols and extra spaces
    import re
    name = re.sub(r"[^\w\s\-’']", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _player_line(p: Any) -> str:
    name = getattr(p, "name", "Unknown")
    pts = getattr(p, "points", None)
    proj = getattr(p, "projected_total_points", None) or getattr(p, "projected_points", None)
    if pts is None:  # some espn_api versions use total_points
        pts = getattr(p, "total_points", None)
    if proj is None:
        return f"{name} ({pts} pts)"
    return f"{name} ({pts} vs {proj} proj)"


def _matchup_context(m: Any) -> Dict[str, Any]:
    home = getattr(m, "home_team", None)
    away = getattr(m, "away_team", None)
    ctx: Dict[str, Any] = {
        "home_team": normalize_name(getattr(home, "team_name", "Home")) if home else "Home",
        "away_team": normalize_name(getattr(away, "team_name", "Away")) if away else "Away",
        "home_score": getattr(m, "home_score", None),
        "away_score": getattr(m, "away_score", None),
        "home_top": None,
        "away_top": None,
        "home_under": None,
        "away_under": None,
        "home_notes": [],
        "away_notes": [],
    }

    # Derive top scorers / underperformers from starters if available
    def top_and_bust(team: Any):
        starters = getattr(team, "starters", []) or []
        if not starters:
            return None, None
        # top scorer by points
        top = max(starters, key=lambda p: getattr(p, "points", getattr(p, "total_points", 0)) or 0)
        # "bust" by delta projected - actual (largest negative)
        def delta(p):
            pts = getattr(p, "points", getattr(p, "total_points", 0)) or 0
            proj = getattr(p, "projected_total_points", getattr(p, "projected_points", 0)) or 0
            return pts - proj
        bust = min(starters, key=delta)
        return top, bust

    if home:
        t, b = top_and_bust(home)
        ctx["home_top"] = _player_line(t) if t else None
        ctx["home_under"] = _player_line(b) if b else None
        ctx["home_notes"] = [_player_line(p) for p in (getattr(home, "starters", []) or [])[:4]]
    if away:
        t, b = top_and_bust(away)
        ctx["away_top"] = _player_line(t) if t else None
        ctx["away_under"] = _player_line(b) if b else None
        ctx["away_notes"] = [_player_line(p) for p in (getattr(away, "starters", []) or [])[:4]]

    return ctx


def _build_user_content(ctx: Dict[str, Any], year: int, week: int, max_words: int) -> str:
    # Compact but informative natural-language context for the LLM
    lines = []
    lines.append(f"Season {year}, Week {week}.")
    lines.append(f"{ctx['home_team']} ({ctx['home_score']}) vs {ctx['away_team']} ({ctx['away_score']}).")
    if ctx.get("home_top"):
        lines.append(f"Home top: {ctx['home_top']}.")
    if ctx.get("away_top"):
        lines.append(f"Away top: {ctx['away_top']}.")
    if ctx.get("home_under"):
        lines.append(f"Home under: {ctx['home_under']}.")
    if ctx.get("away_under"):
        lines.append(f"Away under: {ctx['away_under']}.")
    if ctx.get("home_notes"):
        lines.append("Home notable starters: " + "; ".join(ctx["home_notes"]) + ".")
    if ctx.get("away_notes"):
        lines.append("Away notable starters: " + "; ".join(ctx["away_notes"]) + ".")
    lines.append(f"Write no more than ~{max_words} words.")
    return "\n".join(lines)


def _call_openai(messages: List[Dict[str, str]]) -> str:
    """
    Supports both new and legacy SDKs. Expects OPENAI_API_KEY in env.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for LLM blurbs.")

    model = os.getenv("GAZETTE_LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"

    if 'OpenAI' in globals() and _OPENAI_IMPORTED:
        client = OpenAI(api_key=api_key)  # new SDK
        resp = client.chat.completions.create(model=model, messages=messages, temperature=0.6)
        return (resp.choices[0].message.content or "").strip()
    elif 'openai' in globals():
        openai.api_key = api_key  # legacy SDK
        resp = openai.ChatCompletion.create(model=model, messages=messages, temperature=0.6)
        return (resp["choices"][0]["message"]["content"] or "").strip()
    else:
        raise RuntimeError("OpenAI Python SDK not installed. Run `pip install openai`.")


def generate_blurbs(league: Any, year: int, week: int, style: str = "sabre", max_words: int = 200) -> List[str]:
    """
    Builds matchup contexts and generates one blurb per matchup.
    """
    # Gather matchups
    matchups = getattr(league, "scoreboard")(week)
    results: List[str] = []

    # Choose system prompt
    if style.lower() == "sabre":
        system_prompt = load_sabre_prompt().replace("{week}", str(week))
    else:
        system_prompt = "You are a concise fantasy football recap writer. Be factual and specific."

    for m in matchups:
        ctx = _matchup_context(m)
        user_content = _build_user_content(ctx, year, week, max_words)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        # Call LLM
        try:
            text = _call_openai(messages)
        except Exception as e:
            # If LLM unavailable, return a compact factual fallback
            text = (
                f"Week {week}: {ctx['away_team']} {ctx['away_score']} at "
                f"{ctx['home_team']} {ctx['home_score']}. "
                f"Top performers — Home: {ctx.get('home_top') or 'N/A'}; "
                f"Away: {ctx.get('away_top') or 'N/A'}. "
                f'Sabre out—see you in Week {week}.'
            )
        results.append(text)

    return results
