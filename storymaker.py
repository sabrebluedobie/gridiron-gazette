from __future__ import annotations
import os
from typing import Any, Dict

SABRE_SIGNATURE = "— Sabre, Gridiron Gazette"

SABRE_STORY_PROMPT = """You are Sabre, the Doberman reporter of the Gridiron Gazette.
Voice: witty, a little savage, but fair. Keep it concise and specific.
Write short spotlights per matchup using the provided stats. No profanity.

Return five lines per matchup:
1) Top Scorer (Home)
2) Top Scorer (Away)
3) Biggest Bust
4) Key Play
5) Defense Note
"""

def _has_openai() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))

def generate_spotlights_for_week(ctx: Dict[str, Any], style: str = "sabre", words: int = 200) -> Dict[str, Dict[str, str]]:
    """
    Returns dict like {"1": {"home": "...", "away": "...", "bust": "...", "key": "...", "def": "..."}, ...}
    If OpenAI is unavailable, we synthesize tight stat-based lines so the template never shows blanks.
    """
    # If no key, synthesize from stats (keeps pipeline robust)
    if not _has_openai():
        out: Dict[str, Dict[str, str]] = {}
        for i in range(1, 8):
            h = ctx.get(f"MATCHUP{i}_HOME")
            a = ctx.get(f"MATCHUP{i}_AWAY")
            if not (h and a):
                continue
            hs = ctx.get(f"MATCHUP{i}_HS", "")
            as_ = ctx.get(f"MATCHUP{i}_AS", "")
            hts = ctx.get(f"MATCHUP{i}_HOME_TOP_SCORER", "")
            htp = ctx.get(f"MATCHUP{i}_HOME_TOP_POINTS", "")
            ats = ctx.get(f"MATCHUP{i}_AWAY_TOP_SCORER", "")
            atp = ctx.get(f"MATCHUP{i}_AWAY_TOP_POINTS", "")
            out[str(i)] = {
                "home": f"Top Scorer (Home): {hts} ({htp})" if hts else "Top Scorer (Home): —",
                "away": f"Top Scorer (Away): {ats} ({atp})" if ats else "Top Scorer (Away): —",
                "bust": "Biggest Bust: —",
                "key": f"Key Play: {h} {hs} vs {a} {as_}",
                "def": "Defense Note: —",
            }
        return out

    # With OpenAI: generate per-matchup spotlights
    try:
        from openai import OpenAI
        client = OpenAI()
        league = ctx.get("LEAGUE_NAME", "League")
        week = ctx.get("WEEK_NUMBER", "")

        blocks: Dict[str, Dict[str, str]] = {}
        for i in range(1, 8):
            h = ctx.get(f"MATCHUP{i}_HOME"); a = ctx.get(f"MATCHUP{i}_AWAY")
            if not (h and a): continue
            payload = {
                "league": league, "week": week,
                "home": h, "away": a,
                "hs": ctx.get(f"MATCHUP{i}_HS", ""), "as": ctx.get(f"MATCHUP{i}_AS", ""),
                "home_top": ctx.get(f"MATCHUP{i}_HOME_TOP_SCORER",""),
                "home_pts": ctx.get(f"MATCHUP{i}_HOME_TOP_POINTS",""),
                "away_top": ctx.get(f"MATCHUP{i}_AWAY_TOP_SCORER",""),
                "away_pts": ctx.get(f"MATCHUP{i}_AWAY_TOP_POINTS",""),
            }
            content = f"{SABRE_STORY_PROMPT}\n\nLeague: {league} Week {week}\nData: {payload}\nWrite ~{max(120, words)} words total."
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.5,
                messages=[{"role":"system","content":"You are Sabre."},
                          {"role":"user","content":content}]
            )
            text = resp.choices[0].message.content.strip()
            # simple line-splitter (5 lines expected; be defensive)
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            def pick(idx: int, default: str) -> str:
                try: return lines[idx]
                except Exception: return default
            blocks[str(i)] = {
                "home": pick(0, "Top Scorer (Home): —"),
                "away": pick(1, "Top Scorer (Away): —"),
                "bust": pick(2, "Biggest Bust: —"),
                "key":  pick(3, "Key Play: —"),
                "def":  pick(4, "Defense Note: —"),
            }
        return blocks
    except Exception:
        # Final safety: fallback to stats
        return generate_spotlights_for_week(ctx, style, words=words)  # type: ignore
