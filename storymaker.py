# storymaker.py
# Uses team_mascots.py descriptions to create short matchup stories + image prompts.

from __future__ import annotations
from typing import Optional, Tuple
import os, textwrap

# storymaker.py

SABRE_STORY_PROMPT = """
Write a ~300-word fantasy football matchup recap in the snarky, sarcastic voice of **Sabre**, the Gridiron Gazette’s Doberman mascot and sideline reporter.

Hard rules:
- Keep team names, emojis, and all formatting EXACTLY as provided (do not alter or normalize anything).
- Use details provided by the caller (scores, top performers, busts, D/ST notes).
- Flow naturally into the Stats Spotlight with a short handoff line from Sabre.

Style & structure (always Sabre narrating; never introduce other mascots):
1) **Opening punch** (1–2 sentences): Sabre sets the scene with a witty jab or sly observation about the matchup.
2) **Breakdown** (3–5 short paragraphs): 
   - Hype the top performers with specific stats and quick, punchy commentary.
   - Roast the bust(s) with a wry aside—still factual, not mean-spirited.
   - Include the defense/D-ST note if present (“saved the day” vs “no help today”).
3) **Close** (1 sentence): A sharp quip or forward-looking remark for next week.

Uniqueness guardrails:
- Vary openings, transitions, and closers across matchups—no stock phrasing, no templated repeats.
- Avoid repeating metaphors within the same issue; rotate imagery and verbs.
- The ONLY line you may repeat between matchups is the last one below.

Stats handoff:
End the recap with: “And if you need the receipts, here’s the Stats Spotlight.” 
(Caller will render the actual Stats Spotlight fields.)

Voice notes:
- Snarky, quick, clever; never cruel.
- Tight sentences, energetic rhythm, vivid verbs.
- No filler. Keep it fun and readable.

Output constraints:
- Target length: 300 words ± 10%.
- Do NOT modify team names or emojis.
"""
# Optional: single-liner Sabre signature you MAY (not must) append sparingly across the issue:
SABRE_SIGNATURE = "—Sabre, your snarky sideline reporter"


# Load mascot descriptions
try:
    from team_mascots import team_mascots as MASCOTS
except Exception:
    MASCOTS = {}

# Optional OpenAI
try:
    from openai import OpenAI
    _OPENAI = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None
except Exception:
    _OPENAI = None


def get_desc(name: str) -> str:
    # Graceful fallback if not found
    return (MASCOTS.get(name)
            or MASCOTS.get(name.strip())
            or "")

def _ai_story(home: str, away: str, hdesc: str, adesc: str, scoreline: str) -> str:
    if not _OPENAI:
        # Simple fallback template
        base = f"{home} vs {away}. {hdesc or home} meets {adesc or away}. Final: {scoreline}."
        return textwrap.shorten(base, width=280, placeholder="…")
    prompt = (
        "Write a vivid, family-friendly, 2–3 sentence mini-story for a fantasy football recap. "
        "Tone: energetic, clever, sports-editorial. Incorporate the two team mascots' vibes and the final score. "
        "Avoid gore or brand names. 85–120 words.\n"
        f"Home: {home} — Mascot vibe: {hdesc or '—'}\n"
        f"Away: {away} — Mascot vibe: {adesc or '—'}\n"
        f"Scoreline: {scoreline}\n"
    )
    try:
        r = _OPENAI.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":prompt}],
            temperature=0.8, max_tokens=280,
        )
        return (r.choices[0].message.content or "").strip()
    except Exception:
        return f"{home} and {away} traded punches all week. Final: {scoreline}."

def build_image_prompts(home: str, away: str, hdesc: str, adesc: str) -> Tuple[str,str]:
    """
    Returns (article_prompt, badge_prompt)
    article_prompt: editorial illustration mixing both vibes
    badge_prompt: clean vector badge (if you want an alt logo look)
    """
    base_style = (
        "high-quality editorial sports illustration, dynamic lighting, clean background, "
        "magazine cover composition, no text, tasteful color harmony"
    )
    article = (
        f"{base_style}. Two opposing fantasy football mascots: "
        f"{home} vibe: {hdesc or 'team spirit'}, vs {away} vibe: {adesc or 'team grit'}. "
        "Suggest rivalry energy without violence; include subtle football visual motifs."
    )
    badge = (
        "vector logo badge, symmetrical crest, clean iconography, minimal colors, "
        "print-ready, no text, no gradients, centered composition. "
        f"Concept blend: {home} ({hdesc or 'spirit'}) + {away} ({adesc or 'grit'})."
    )
    return article, badge

def make_story_and_prompts(home: str, away: str, hs, ascore) -> dict:
    hdesc = get_desc(home)
    adesc = get_desc(away)
    scoreline = f"{home} {hs} – {away} {ascore}"
    story = _ai_story(home, away, hdesc, adesc, scoreline)
    art_prompt, badge_prompt = build_image_prompts(home, away, hdesc, adesc)
    return {
        "story": story,
        "article_prompt": art_prompt,
        "badge_prompt": badge_prompt,
        "home_desc": hdesc,
        "away_desc": adesc,
    }