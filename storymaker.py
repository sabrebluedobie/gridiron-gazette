"""
storymaker.py — Sabre voice blurbs via OpenAI (or compact fallback).

- Loads Sabre voice prompt from prompts/sabre_voice.txt or ENV override.
- Builds lightweight matchup context from the espn_api League object.
- Uses OpenAI Chat Completions; supports new SDK (OpenAI) or legacy (openai).
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import List, Dict, Any

# Try new SDK first
_OPENAI_NEW = False
try:
    from openai import OpenAI  # type: ignore
    _OPENAI_NEW = True
except Exception:
    pass

# Fallback legacy
if not _OPENAI_NEW:
    try:
        import openai  # type: ignore
    except Exception:
        openai = None


def _load_sabre_prompt() -> str:
    env_text = os.getenv("GAZETTE_SABRE_PROMPT")
    if env_text and env_text.strip():
        return env_text.strip()

    for p in (Path("prompts") / "sabre_voice.txt", Path("config") / "sabre_voice.txt"):
        if p.exists():
            try:
                return p.read_text(encoding="utf-8").strip()
            except Exception:
                pass

    # Safe default (short)
    return (
        "You are Sabre, the Gridiron Gazette’s Doberman mascot and beat reporter. "
        "Voice: hard-working, witty, family-friendly. First person as Sabre. "
        "No invented stats; only use provided data. "
        "Call out swing play, top scorers, underperformers vs projection, and any decisive lineup choice. "
        "Aim ~200 words. End with ‘Sabre out—see you in Week {week}.’"
    )


def _norm_name(s: str) -> str:
    import re, unicodedata
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[^\w\s\-’']", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _player_line(p: Any) -> str:
    name = getattr(p, "name", "Unknown")
    pts = getattr(p, "points", getattr(p, "total_points", 0)) or 0
    proj = getattr(p, "projected_total_points", getattr(p, "projected_points", 0)) or 0
    if proj:
        return f"{name} ({pts:.1f} vs {proj:.1f} proj)"
    return f"{name} ({pts:.1f} pts)"


def _matchup_ctx(m: Any, year: int, week: int, max_words: int) -> Dict[str, str]:
    h = getattr(m, "home_team", None)
    a = getattr(m, "away_team", None)
    hs = getattr(m, "home_score", None)
    as_ = getattr(m, "away_score", None)

    def top(team):
        starters = getattr(team, "starters", []) or []
        if not starters: return None, None
        # top, bust by projected delta
        top_p = max(starters, key=lambda p: getattr(p, "points", getattr(p, "total_points", 0)) or 0)
        bust_p = min(starters, key=lambda p: (getattr(p, "points", getattr(p, "total_points", 0)) or 0) - (getattr(p, "projected_total_points", getattr(p, "projected_points", 0)) or 0))
        return _player_line(top_p), _player_line(bust_p)

    ht, hb = top(h) if h else (None, None)
    at, ab = top(a) if a else (None, None)

    parts = [
        f"Season {year}, Week {week}.",
        f"{_norm_name(getattr(h,'team_name','Home'))} ({hs}) vs {_norm_name(getattr(a,'team_name','Away'))} ({as_}).",
    ]
    if ht: parts.append(f"Home top: {ht}.")
    if at: parts.append(f"Away top: {at}.")
    if hb: parts.append(f"Home under: {hb}.")
    if ab: parts.append(f"Away under: {ab}.")
    parts.append(f"Write no more than ~{max_words} words.")
    return {"user": "\n".join(parts)}


def _call_openai(messages: List[Dict[str, str]]) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for LLM blurbs.")
    model = os.getenv("GAZETTE_LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"

    if _OPENAI_NEW:
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(model=model, messages=messages, temperature=0.6)
        return (resp.choices[0].message.content or "").strip()
    if openai is not None:
        openai.api_key = api_key
        resp = openai.ChatCompletion.create(model=model, messages=messages, temperature=0.6)
        return (resp["choices"][0]["message"]["content"] or "").strip()
    raise RuntimeError("OpenAI Python SDK not installed. Run `pip install openai`.")


def generate_blurbs(league: Any, year: int, week: int, style: str = "sabre", max_words: int = 200) -> List[str]:
    board = league.scoreboard(week)
    out: List[str] = []

    if style.lower() == "sabre":
        system_prompt = _load_sabre_prompt().replace("{week}", str(week))
    else:
        system_prompt = "You are a concise fantasy football recap writer. Be factual and specific."

    for m in board:
        u = _matchup_ctx(m, year, week, max_words)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": u["user"]},
        ]
        try:
            out.append(_call_openai(messages))
        except Exception as e:
            # Compact factual fallback
            h = getattr(m, "home_team", None)
            a = getattr(m, "away_team", None)
            hs = getattr(m, "home_score", None)
            as_ = getattr(m, "away_score", None)
            out.append(
                f"Week {week}: {getattr(a,'team_name','Away')} {as_} at {getattr(h,'team_name','Home')} {hs}. "
                f"Sabre out—see you in Week {week}."
            )
    return out
