"""
storymaker.py — Gridiron Gazette
--------------------------------
Generates Sabre-style recaps and short blurbs using an injected LLM callable.

Usage (example):

    from storymaker import StoryMaker, MatchupData

    def my_llm(messages, temperature=0.8, top_p=0.9, max_tokens=800):
        # Wrap your provider here (OpenAI, Azure, etc.). Must return a string.
        ...

    maker = StoryMaker(llm=my_llm)
    recap = maker.generate_recap(matchup_data)
    blurb = maker.generate_blurb(matchup_data)

This file embeds the updated Sabre prompt with:
- Recaps: 200–250 words, 2–3 paragraphs, 3–5 sentences each
- Short blurbs: 1–2 sentences (25–45 words)
- New sign-off with paw print
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol, Any
import json
import re
import textwrap

# ============================
# Sabre Prompt (source of truth)
# ============================
SABRE_PROMPT_YAML = textwrap.dedent(
    """
    Sabre Prompt:
      role: mascot-reporter
      persona: "Sabre — cropped-and-docked blue (grey) Doberman; Gazette’s loud-mouthed mascot who thinks he’s ESPN’s funniest analyst."
      goals:
        - Deliver accurate game recaps and matchup blurbs using real stats.
        - Make readers laugh out loud with jabs, zingers, and football-fluent metaphors.
        - Keep it punchy, readable, and hype-worthy for social + PDF.
      tone: "snarky, witty, sharp; like a late-night sports commentator on triple espresso"
      style: "playful but credible; roast the play, not the person; PG-13 funny"
      guardrails:
        - No cruelty, slurs, or personal attacks. Roast decisions/plays, not identities.
        - Avoid repetitive jokes across a single issue (rotate metaphors and bits).
        - Keep team and player names accurate; do not hallucinate stats.
        - When stats are unknown, use colorful but clearly non-fabricated phrasing.

      structure:
        - "For recaps: 200–250 words, split into 2–3 paragraphs."
        - "Each paragraph: 3–5 sentences."
        - "Open with a one-liner hook: a punchline or vivid metaphor."
        - "Middle paragraphs: highlight stats, key swings, and coaching/player decisions with snark."
        - "Close with a kicker joke or hype line."
        - "For short blurbs: 1–2 sentences, focused on one sharp punchline or observation."

      length:
        short_blurb: "1–2 sentences, 25–45 words"
        recap: "200–250 words, 2–3 paragraphs, 3–5 sentences each"

      joke_cadence:
        - "At least 1 strong joke per 2 sentences."
        - "Mix: 1 metaphor, 1 jab, optional 4th-wall aside."

      rhetorical_devices:
        - metaphors: ["folded like a lawn chair in a hurricane", "tackled like a coupon in Black Friday"]
        - comparisons: ["like my tail when the treat jar pops", "like a punt into a headwind"]
        - fourth_wall: ["Sabre here—I don’t make the rules, I just howl them."]

      must_include:
        - "One concrete detail: {stat_line|swing|injury_note|bench_mistake}."
        - "One metaphor or simile."
        - "One clean jab that targets a play/decision (not a person’s identity)."
        - "Clear outcome or implication (why it mattered)."

      signoff:
        pattern: "—Sabre, your hilariously snarky 4-legged Gridiron Gazette reporter 🐾"
        usage: "Add on the final line for end-of-section recaps; omit in tight lists."
    """
).strip()

SABRE_SIGNOFF = "—Sabre, your hilariously snarky 4-legged Gridiron Gazette reporter 🐾"

# A structured mirror of key prompt bits for programmatic assembly
SABRE_PROMPT: Dict[str, Any] = {
    "role": "mascot-reporter",
    "persona": "Sabre — cropped-and-docked blue (grey) Doberman; Gazette’s loud-mouthed mascot who thinks he’s ESPN’s funniest analyst.",
    "tone": "snarky, witty, sharp; like a late-night sports commentator on triple espresso",
    "style": "playful but credible; roast the play, not the person; PG-13 funny",
    "structure": [
        "For recaps: 200–250 words, split into 2–3 paragraphs.",
        "Each paragraph: 3–5 sentences.",
        "Open with a one-liner hook: a punchline or vivid metaphor.",
        "Middle paragraphs: highlight stats, key swings, and coaching/player decisions with snark.",
        "Close with a kicker joke or hype line.",
        "For short blurbs: 1–2 sentences, focused on one sharp punchline or observation.",
    ],
    "length": {
        "short_blurb": "1–2 sentences, 25–45 words",
        "recap": "200–250 words, 2–3 paragraphs, 3–5 sentences each",
    },
    "signoff": {
        "pattern": SABRE_SIGNOFF,
        "usage": "Add on the final line for end-of-section recaps; omit in tight lists.",
    },
}

# ===============
# Data structures
# ===============
@dataclass
class PlayerStat:
    name: str
    position: Optional[str] = None
    line: Optional[str] = None  # e.g., "8 rec, 124 yds, 2 TD"
    team: Optional[str] = None

@dataclass
class MatchupData:
    league_name: str
    week: int
    team_a: str
    team_b: str
    score_a: Optional[float] = None
    score_b: Optional[float] = None
    top_performers: List[PlayerStat] = field(default_factory=list)
    turnovers_a: Optional[int] = None
    turnovers_b: Optional[int] = None
    big_plays: List[str] = field(default_factory=list)  # e.g., "75-yd TD by X in Q3"
    projection_swing: Optional[float] = None  # e.g., +22.4 vs projection for winner
    injury_notes: List[str] = field(default_factory=list)
    bench_mistakes: List[str] = field(default_factory=list)  # e.g., "Left Player X (21.4) on bench"
    winner: Optional[str] = None
    margin: Optional[float] = None

# ==========
# LLM types
# ==========
class LLM(Protocol):
    def __call__(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.8,
        top_p: float = 0.9,
        max_tokens: int = 800,
    ) -> str: ...

# ===================
# Utility helpers
# ===================
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w[\w'\-]*\b", text))


def _ensure_paragraphs(text: str, target_paras: int = 2) -> str:
    paras = [p.strip() for p in re.split(r"\n{2,}", text.strip()) if p.strip()]
    if len(paras) >= target_paras:
        return "\n\n".join(paras)

    # If a single block, attempt to split by sentences into 2–3 paragraphs
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(sentences) >= 6:
        # 2–3 paragraphs: split roughly in half
        mid = len(sentences) // 2
        p1 = " ".join(sentences[:mid])
        p2 = " ".join(sentences[mid:])
        return f"{p1}\n\n{p2}"
    return text


def _trim_to_words(text: str, min_words: int, max_words: int) -> str:
    words = re.findall(r"\S+", text)
    if len(words) > max_words:
        text = " ".join(words[:max_words])
        # Ensure clean ending
        text = re.sub(r"[\s,;:]+$", ".", text).strip()
    # If too short, we accept; LLM should mostly obey. Caller may re-ask if needed.
    return text


def _append_signoff(text: str) -> str:
    text = text.rstrip()
    if not text.endswith(SABRE_SIGNOFF):
        text += f"\n\n{SABRE_SIGNOFF}"
    return text


# ==================
# Message assembly
# ==================
SYSTEM_BASE = (
    "You are Sabre, the Gridiron Gazette’s mascot-reporter. "
    "Persona: cropped-and-docked blue (grey) Doberman; loud-mouthed, witty, but credible. "
    "Tone: snarky, witty, sharp; late-night sports commentator on triple espresso. "
    "Style: roast the play, not the person; PG-13; mix real stats with jokes. "
)

STRUCTURE_RULES = (
    "Recaps must be 200–250 words in 2–3 paragraphs, 3–5 sentences each paragraph. "
    "Open with a one-liner hook; include at least one precise stat or factual detail, "
    "one metaphor/simile, one clean jab at a decision/play, and a clear outcome/implication. "
    "Close with a kicker line. Short blurbs must be 1–2 sentences and 25–45 words."
)


def _matchup_json(data: MatchupData) -> str:
    safe = {
        "league_name": data.league_name,
        "week": data.week,
        "teams": {"a": data.team_a, "b": data.team_b},
        "score": {"a": data.score_a, "b": data.score_b},
        "winner": data.winner,
        "margin": data.margin,
        "top_performers": [vars(p) for p in data.top_performers],
        "turnovers": {"a": data.turnovers_a, "b": data.turnovers_b},
        "big_plays": data.big_plays,
        "projection_swing": data.projection_swing,
        "injury_notes": data.injury_notes,
        "bench_mistakes": data.bench_mistakes,
    }
    return json.dumps(safe, ensure_ascii=False)


def _build_messages(task: str, data: MatchupData) -> List[Dict[str, str]]:
    assert task in {"recap", "blurb"}
    instructions = STRUCTURE_RULES
    content = (
        f"Task: Write a {task} for Week {data.week} in league '{data.league_name}'.\n"
        f"Teams: {data.team_a} vs. {data.team_b}.\n"
        f"JSON facts (ground truth; do not fabricate): {_matchup_json(data)}\n"
        "Do not invent stats. If a stat is missing, be colorful without fabricating numbers.\n"
        "Required: at least one concrete detail (stat line, swing, injury, or bench mistake).\n"
    )

    if task == "recap":
        content += (
            "Follow recap length rules. End with this exact sign-off on the final line: "
            f"{SABRE_SIGNOFF}\n"
        )
    else:
        content += (
            "Produce 1–2 sentences (25–45 words). No sign-off for short blurbs.\n"
        )

    return [
        {"role": "system", "content": SYSTEM_BASE + instructions},
        {"role": "user", "content": content},
    ]


# ==================
# Main generator API
# ==================
class StoryMaker:
    def __init__(self, llm: Optional[LLM] = None):
        self.llm = llm

    # ---------- Public API ----------
    def generate_recap(
        self,
        data: MatchupData,
        temperature: float = 0.9,
        top_p: float = 0.9,
        max_tokens: int = 900,
        enforce_bounds: bool = True,
    ) -> str:
        """Create a Sabre recap (200–250 words, 2–3 paragraphs) with sign-off."""
        if self.llm is None:
            # Fallback template if no LLM is provided
            return self._template_recap(data)

        messages = _build_messages("recap", data)
        draft = self.llm(messages, temperature=temperature, top_p=top_p, max_tokens=max_tokens)
        draft = draft.strip()

        if enforce_bounds:
            draft = _ensure_paragraphs(draft, target_paras=2)
            draft = _trim_to_words(draft, min_words=200, max_words=250)
            draft = _append_signoff(draft)
        return draft

    def generate_blurb(
        self,
        data: MatchupData,
        temperature: float = 0.9,
        top_p: float = 0.9,
        max_tokens: int = 200,
        enforce_bounds: bool = True,
    ) -> str:
        """Create a Sabre short blurb (1–2 sentences, 25–45 words)."""
        if self.llm is None:
            return self._template_blurb(data)

        messages = _build_messages("blurb", data)
        draft = self.llm(messages, temperature=temperature, top_p=top_p, max_tokens=max_tokens)
        draft = draft.strip()

        if enforce_bounds:
            words = _word_count(draft)
            if words < 25 or words > 45:
                # Light trim/expand—simple heuristic
                draft = _trim_to_words(draft, min_words=25, max_words=45)
            # Remove any accidental sign-off
            draft = draft.replace(SABRE_SIGNOFF, "").strip()
        return draft

    # ---------- Fallback templates (no-LLM mode) ----------
    def _template_recap(self, d: MatchupData) -> str:
        hook = (
            f"This one played less like chess and more like bumper cars—{d.team_a} and {d.team_b} turned chaos into content."
        )
        facts = []
        if d.score_a is not None and d.score_b is not None:
            facts.append(f"Final: {d.team_a} {d.score_a:.1f} — {d.team_b} {d.score_b:.1f}.")
        if d.winner and d.margin is not None:
            facts.append(f"{d.winner} took it by {d.margin:.1f}.")
        if d.projection_swing:
            facts.append(f"Projection swing: {d.projection_swing:+.1f}.")
        if d.turnovers_a is not None:
            facts.append(f"{d.team_a} turnovers: {d.turnovers_a}.")
        if d.turnovers_b is not None:
            facts.append(f"{d.team_b} turnovers: {d.turnovers_b}.")
        if d.big_plays:
            facts.append("Big plays: " + "; ".join(d.big_plays) + ".")
        if d.injury_notes:
            facts.append("Injuries: " + "; ".join(d.injury_notes) + ".")
        if d.bench_mistakes:
            facts.append("Bench blunders: " + "; ".join(d.bench_mistakes) + ".")
        if d.top_performers:
            tp = ", ".join(
                f"{p.name} ({p.position or ''}) {p.line or ''}".strip() for p in d.top_performers
            )
            facts.append("Top performers: " + tp + ".")

        mid1 = (
            " ".join(facts[:max(1, len(facts)//2)])
            or f"{d.team_a} found bursts, {d.team_b} found answers—nobody found brakes."
        )
        mid2 = (
            " ".join(facts[max(1, len(facts)//2):])
            or "Both sidelines made choices that aged like milk, but the winners cashed in when it counted."
        )
        kicker = (
            "Call it chaos football—hilarious for neutrals, nerve-wracking for fans."
        )

        body = f"{hook} {mid1}\n\n{mid2} {kicker}"
        body = _trim_to_words(body, min_words=200, max_words=250)
        body = _append_signoff(body)
        return body

    def _template_blurb(self, d: MatchupData) -> str:
        core = f"{d.team_a} vs. {d.team_b}: a yo-yo of momentum and questionable decisions."
        if d.winner:
            core += f" {d.winner} escapes with the W; film rooms get busy tomorrow."
        return _trim_to_words(core, min_words=25, max_words=45)


# -----------------
# CLI convenience
# -----------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate Sabre stories from JSON input.")
    parser.add_argument("matchup_json", help="Path to JSON file with MatchupData fields")
    parser.add_argument("--mode", choices=["recap", "blurb"], default="recap")
    args = parser.parse_args()

    with open(args.matchup_json, "r", encoding="utf-8") as f:
        payload = json.load(f)

    # Convert JSON to dataclasses
    top_performers = [PlayerStat(**p) for p in payload.get("top_performers", [])]
    data = MatchupData(
        league_name=payload["league_name"],
        week=payload["week"],
        team_a=payload["team_a"],
        team_b=payload["team_b"],
        score_a=payload.get("score_a"),
        score_b=payload.get("score_b"),
        top_performers=top_performers,
        turnovers_a=payload.get("turnovers_a"),
        turnovers_b=payload.get("turnovers_b"),
        big_plays=payload.get("big_plays", []),
        projection_swing=payload.get("projection_swing"),
        injury_notes=payload.get("injury_notes", []),
        bench_mistakes=payload.get("bench_mistakes", []),
        winner=payload.get("winner"),
        margin=payload.get("margin"),
    )

    # No LLM wired on CLI—use templates
    maker = StoryMaker(llm=None)
    if args.mode == "recap":
        print(maker.generate_recap(data))
    else:
        print(maker.generate_blurb(data))
