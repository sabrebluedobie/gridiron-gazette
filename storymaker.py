from __future__ import annotations
import os
from typing import List, Dict, Any

_OPENAI_NEW = False
try:
    from openai import OpenAI
    _OPENAI_NEW = True
except Exception:
    pass

if not _OPENAI_NEW:
    try:
        import openai  # type: ignore
    except Exception:
        openai = None

def _load_sabre_prompt(week: int) -> str:
    p = os.getenv("GAZETTE_SABRE_PROMPT")
    if p: return p.strip()
    return (
        f"You are Sabre, the Gridiron Gazette’s Doberman mascot and beat reporter. "
        f"Voice: witty, clean, first-person as Sabre. "
        f"Do not invent stats. Focus on the info provided. "
        f"Call out the decisive swing, top effort, and any letdown. "
        f"End with ‘Sabre out—see you in Week {week}.’"
    )

def _player_line(p: Any) -> str:
    pts = getattr(p,"points", getattr(p,"total_points",0)) or 0
    proj = getattr(p,"projected_total_points", getattr(p,"projected_points",0)) or 0
    name = getattr(p,"name","Unknown")
    return f"{name} ({pts:.1f} vs {proj:.1f} proj)" if proj else f"{name} ({pts:.1f} pts)"

def _from_league_matchup(m: Any, year: int, week: int, max_words: int) -> str:
    h, a = getattr(m,"home_team",None), getattr(m,"away_team",None)
    hs, as_ = getattr(m,"home_score",0), getattr(m,"away_score",0)
    lines = [f"Season {year}, Week {week}. {getattr(h,'team_name','Home')} ({hs}) vs {getattr(a,'team_name','Away')} ({as_})."]
    for t, label in ((h,"Home"),(a,"Away")):
        st = getattr(t,"starters",[]) or []
        if st:
            top = max(st, key=lambda p: getattr(p,"points", getattr(p,"total_points",0)) or 0)
            lines.append(f"{label} top: {_player_line(top)}.")
    lines.append(f"Write ~{max_words} words.")
    return "\n".join(lines)

def _from_games_entry(g: Dict[str, Any], year: int, week: int, max_words: int) -> str:
    h, a = g.get("HOME_TEAM_NAME","Home"), g.get("AWAY_TEAM_NAME","Away")
    hs, as_ = g.get("HOME_SCORE","0"), g.get("AWAY_SCORE","0")
    return (f"Season {year}, Week {week}. {h} ({hs}) vs {a} ({as_}). "
            f"Use only this info. Write ~{max_words} words.")

def _call_openai(messages: List[Dict[str,str]]) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY missing")
    model = os.getenv("GAZETTE_LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
    if _OPENAI_NEW:
        resp = OpenAI(api_key=api_key).chat.completions.create(model=model, messages=messages, temperature=0.6)
        return (resp.choices[0].message.content or "").strip()
    if 'openai' in globals() and openai:
        openai.api_key = api_key
        resp = openai.ChatCompletion.create(model=model, messages=messages, temperature=0.6)
        return (resp["choices"][0]["message"]["content"] or "").strip()
    raise RuntimeError("OpenAI SDK not installed")

def generate_blurbs(
    league: Any,
    year: int,
    week: int,
    style: str = "sabre",
    max_words: int = 200,
    games: List[Dict[str,Any]] | None = None,   # NEW: use team scores if league not available
) -> List[str]:
    sys_prompt = _load_sabre_prompt(week) if style.lower()=="sabre" else "You write concise, factual fantasy recaps."
    out: List[str] = []
    used_fallback = False

    # Try league-based context first (with players)
    try:
        if league:
            board = league.scoreboard(week)
            for m in board:
                messages = [{"role":"system","content":sys_prompt},
                            {"role":"user","content":_from_league_matchup(m, year, week, max_words)}]
                out.append(_call_openai(messages))
            return out
    except Exception:
        used_fallback = True

    # Fallback: use team scores from games (no player details)
    if games:
        for g in games:
            messages = [{"role":"system","content":sys_prompt},
                        {"role":"user","content":_from_games_entry(g, year, week, max_words)}]
            try:
                out.append(_call_openai(messages))
            except Exception:
                h, a = g.get("HOME_TEAM_NAME","Home"), g.get("AWAY_TEAM_NAME","Away")
                hs, as_ = g.get("HOME_SCORE","0"), g.get("AWAY_SCORE","0")
                out.append(f"Week {week}: {h} {hs} vs {a} {as_}. Sabre out—see you in Week {week}.")
        return out

    # Last resort
    if used_fallback:
        return [f"Week {week} wrapped. Sabre out—see you in Week {week}."] * 6
    return out
