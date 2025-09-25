"""
storymaker.py — Gridiron Gazette
--------------------------------
Generates Sabre-style recaps and short blurbs using an injected LLM callable.
INCLUDES MARKDOWN TO FORMATTED TEXT CONVERSION

• Recaps: 200–250 words, 2–3 paragraphs, 3–5 sentences each paragraph.
• Short blurbs: 1–2 sentences (25–45 words).
• New sign-off (with paw print) auto-appended to recaps.
• Converts markdown formatting to clean text for DOCX

Usage:

    from storymaker import StoryMaker, MatchupData

    def my_llm(messages, temperature=0.8, top_p=0.9, max_tokens=800):
        # Wrap your provider here (OpenAI, Azure, etc.). Must return a string.
        ...

    maker = StoryMaker(llm=my_llm)
    recap = maker.generate_recap(matchup_data)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol, Any
import json
import re
import textwrap
import logging

logger = logging.getLogger(__name__)

# ============================
# Sabre Prompt (source of truth)
# ============================
SABRE_SIGNOFF = "—Sabre, your hilariously snarky 4-legged Gridiron Gazette reporter 🐾"

SABRE_PROMPT: Dict[str, Any] = {
    "role": "mascot-reporter",
    "persona": "Sabre — the Gazette's sharp-tongued sports analyst who happens to be a Doberman. Think ESPN analyst first, mascot second.",
    "goals": [
        "Deliver accurate game recaps and matchup blurbs using real stats.",
        "Make readers laugh out loud with creative metaphors, sports references, and clever observations.",
        "Keep it punchy, readable, and hype-worthy for social + PDF.",
    ],
    "tone": "snarky, witty, sharp; like a late-night sports commentator on triple espresso",
    "style": "sports-focused humor; creative comparisons from all walks of life; roast the play, not the person; PG-13 funny",
    "humor_guidelines": [
        "Primary focus: sports commentary, game analysis, creative metaphors",
        "Use diverse comparisons: food, weather, pop culture, everyday life, technology, etc.",
        "Dog references: sparingly (max 1 per recap) - you're a sports analyst who happens to be a dog",
        "Avoid repetitive animal puns - mix up your metaphor sources",
        "Think like a human sports commentator with a sharp wit",
    ],
    "guardrails": [
        "No cruelty, slurs, or personal attacks. Roast decisions/plays, not identities.",
        "Avoid repetitive jokes across a single issue (rotate metaphors and bits).",
        "Keep team and player names accurate; do not hallucinate stats.",
        "When stats are unknown, be colorful without fabricating numbers.",
        "Vary your comparison sources - not everything needs to be dog-related.",
    ],
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
    "joke_cadence": [
        "At least 1 strong joke per 2 sentences.",
        "Mix: sports metaphors, pop culture refs, creative comparisons, occasional 4th-wall aside.",
    ],
    "rhetorical_devices": {
        "sports_metaphors": ["folded like a defense in the red zone", "crumbled like a prevent defense in the fourth"],
        "creative_comparisons": ["tighter than a playoff race", "shakier than a rookie kicker", "smoother than Sunday morning coffee"],
        "pop_culture": ["like a Netflix series that got cancelled mid-season", "like trying to return something to Amazon without a receipt"],
        "food_refs": ["cooked like a Thanksgiving turkey", "served up colder than yesterday's pizza"],
        "fourth_wall": ["I've seen more excitement in a punt formation", "Even I could've made that call with my eyes closed"],
    },
    "must_include": [
        "One concrete detail: {stat_line|swing|injury_note|bench_mistake}.",
        "One creative metaphor or comparison (not necessarily dog-related).",
        "One clean jab that targets a play/decision (not a person's identity).",
        "Clear outcome or implication (why it mattered).",
    ],
    "signoff": {
        "pattern": SABRE_SIGNOFF,
        "usage": "Add on the final line for end-of-section recaps; omit in tight lists.",
    },
}

# ===============================
# MARKDOWN CONVERSION FUNCTIONS
# ===============================

def clean_markdown_for_docx(text: str) -> str:
    """
    Convert markdown formatting to plain text for DOCX templates.
    Removes markdown syntax while preserving the actual content.
    
    Examples:
        **Bold Text** -> Bold Text
        *Italic Text* -> Italic Text
        ### Header -> Header
        `Code` -> Code
    """
    if not text:
        return text
    
    # Store original for comparison
    original = text
    
    # Remove bold markdown (**text** or __text__ -> text)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    
    # Remove italic markdown (*text* or _text_ -> text)
    # Be careful not to remove single asterisks that aren't markdown
    text = re.sub(r'(?<!\*)\*(?!\*)([^\*]+)\*(?!\*)', r'\1', text)
    text = re.sub(r'(?<!_)_(?!_)([^_]+)_(?!_)', r'\1', text)
    
    # Remove code backticks (`text` -> text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    
    # Remove headers (### text -> text)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    
    # Remove strikethrough (~~text~~ -> text)
    text = re.sub(r'~~(.*?)~~', r'\1', text)
    
    # Remove blockquotes (> text -> text)
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    
    # Remove horizontal rules
    text = re.sub(r'^[\-\*_]{3,}$', '', text, flags=re.MULTILINE)
    
    # Clean up any remaining artifacts
    text = text.strip()
    
    if text != original:
        logger.debug(f"Cleaned markdown: '{original[:50]}...' -> '{text[:50]}...'")
    
    return text

def clean_all_markdown_in_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively clean markdown from all string values in a dictionary.
    Returns a new dictionary with cleaned values.
    """
    cleaned = {}
    for key, value in data.items():
        if isinstance(value, str):
            cleaned[key] = clean_markdown_for_docx(value)
        elif isinstance(value, dict):
            cleaned[key] = clean_all_markdown_in_dict(value)
        elif isinstance(value, list):
            cleaned[key] = [
                clean_markdown_for_docx(item) if isinstance(item, str) else item
                for item in value
            ]
        else:
            cleaned[key] = value
    return cleaned

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
    big_plays: List[str] = field(default_factory=list)
    projection_swing: Optional[float] = None
    injury_notes: List[str] = field(default_factory=list)
    bench_mistakes: List[str] = field(default_factory=list)
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
def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w[\w'\-]*\b", text))

def _ensure_paragraphs(text: str, target_paras: int = 2) -> str:
    paras = [p.strip() for p in re.split(r"\n{2,}", text.strip()) if p.strip()]
    if len(paras) >= target_paras:
        return "\n\n".join(paras)
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(sentences) >= 6:
        mid = len(sentences) // 2
        p1 = " ".join(sentences[:mid])
        p2 = " ".join(sentences[mid:])
        return f"{p1}\n\n{p2}"
    return text

def _trim_to_words(text: str, min_words: int, max_words: int) -> str:
    words = re.findall(r"\S+", text)
    if len(words) > max_words:
        text = " ".join(words[:max_words])
        text = re.sub(r"[\s,;:]+$", ".", text).strip()
    return text

def _append_signoff(text: str) -> str:
    """Append Sabre's signature if not already present."""
    text = text.rstrip()
    if not text.endswith(SABRE_SIGNOFF):
        text += f"\n\n{SABRE_SIGNOFF}"
    return text

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

# ==================
# Message assembly
# ==================
SYSTEM_BASE = (
    "You are Sabre, the Gridiron Gazette's mascot-reporter. "
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

def _build_messages(task: str, data: MatchupData) -> List[Dict[str, str]]:
    assert task in {"recap", "blurb"}
    content = (
        f"Task: Write a {task} for Week {data.week} in league '{data.league_name}'.\n"
        f"Teams: {data.team_a} vs. {data.team_b}.\n"
        f"JSON facts (ground truth; do not fabricate): {_matchup_json(data)}\n"
        "Do not invent stats. If a stat is missing, be colorful without fabricating numbers.\n"
        "Required: at least one concrete detail (stat line, swing, injury, or bench mistake).\n"
    )
    if task == "recap":
        content += f"End with this exact sign-off on the final line: {SABRE_SIGNOFF}\n"
    else:
        content += "Produce 1–2 sentences (25–45 words). No sign-off for short blurbs.\n"

    return [
        {"role": "system", "content": SYSTEM_BASE + " " + STRUCTURE_RULES},
        {"role": "user", "content": content},
    ]

# ==================
# Main generator API
# ==================
class StoryMaker:
    def __init__(self, llm: Optional[LLM] = None):
        self.llm = llm

    def generate_recap(
        self,
        data: MatchupData,
        temperature: float = 0.9,
        top_p: float = 0.9,
        max_tokens: int = 900,
        enforce_bounds: bool = True,
        clean_markdown: bool = True,  # NEW: Auto-clean markdown
    ) -> str:
        """
        Create a Sabre recap (200–250 words, 2–3 paragraphs) with sign-off.
        Automatically cleans markdown formatting for DOCX output.
        """
        if self.llm is None:
            recap = self._template_recap(data)
        else:
            messages = _build_messages("recap", data)
            draft = (self.llm(messages, temperature=temperature, top_p=top_p, max_tokens=max_tokens) or "").strip()
            
            if enforce_bounds:
                if _word_count(draft) < 120:
                    draft = self._template_recap(data)
                draft = _ensure_paragraphs(draft, target_paras=2)
                draft = _trim_to_words(draft, min_words=200, max_words=250)
                draft = _append_signoff(draft)
            
            recap = draft
        
        # Clean markdown formatting if requested
        if clean_markdown:
            recap = clean_markdown_for_docx(recap)
            logger.debug(f"Cleaned markdown from recap for {data.team_a} vs {data.team_b}")
        
        return recap

    def generate_blurb(
        self,
        data: MatchupData,
        temperature: float = 0.9,
        top_p: float = 0.9,
        max_tokens: int = 200,
        enforce_bounds: bool = True,
        clean_markdown: bool = True,  # NEW: Auto-clean markdown
    ) -> str:
        """
        Create a Sabre short blurb (1–2 sentences, 25–45 words).
        Automatically cleans markdown formatting for DOCX output.
        """
        if self.llm is None:
            blurb = self._template_blurb(data)
        else:
            messages = _build_messages("blurb", data)
            draft = (self.llm(messages, temperature=temperature, top_p=top_p, max_tokens=max_tokens) or "").strip()
            
            if enforce_bounds:
                if _word_count(draft) < 20:
                    draft = self._template_blurb(data)
                # Remove any accidental sign-off
                draft = draft.replace(SABRE_SIGNOFF, "").strip()
                draft = _trim_to_words(draft, min_words=25, max_words=45)
            
            blurb = draft
        
        # Clean markdown formatting if requested
        if clean_markdown:
            blurb = clean_markdown_for_docx(blurb)
            logger.debug(f"Cleaned markdown from blurb for {data.team_a} vs {data.team_b}")
        
        return blurb

    # ---------- Fallback templates (no-LLM mode) ----------
    def _template_recap(self, d: MatchupData) -> str:
        """Fallback template when no LLM is available."""
        hook = f"This one played less like chess and more like bumper cars—{d.team_a} and {d.team_b} turned chaos into content."
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
            tp = ", ".join(f"{p.name} {('(' + p.position + ') ') if p.position else ''}{p.line or ''}".strip() for p in d.top_performers)
            facts.append("Top performers: " + tp + ".")

        mid1 = " ".join(facts[:max(1, len(facts)//2)]) or f"{d.team_a} found bursts, {d.team_b} found answers—nobody found brakes."
        mid2 = " ".join(facts[max(1, len(facts)//2):]) or "Both sidelines made choices that aged like milk, but the winners cashed in when it counted."
        kicker = "Call it chaos football—hilarious for neutrals, nerve-wracking for fans."

        body = f"{hook} {mid1}\n\n{mid2} {kicker}"
        body = _trim_to_words(body, min_words=200, max_words=250)
        body = _append_signoff(body)
        return body

    def _template_blurb(self, d: MatchupData) -> str:
        """Fallback template for short blurbs when no LLM is available."""
        core = f"{d.team_a} vs. {d.team_b}: a yo-yo of momentum and questionable decisions."
        if d.winner:
            core += f" {d.winner} escapes with the W; film rooms get busy tomorrow."
        return _trim_to_words(core, min_words=25, max_words=45)

# ==================
# Testing utilities
# ==================

def test_markdown_conversion():
    """Test the markdown conversion functionality."""
    test_cases = [
        ("**Bold Text**", "Bold Text"),
        ("*Italic Text*", "Italic Text"),
        ("__Also Bold__", "Also Bold"),
        ("_Also Italic_", "Also Italic"),
        ("`Code Text`", "Code Text"),
        ("### Header Text", "Header Text"),
        ("~~Strikethrough~~", "Strikethrough"),
        ("> Quoted text", "Quoted text"),
        ("**Top Play**: The big moment", "Top Play: The big moment"),
        ("Normal text with **bold** and *italic* mixed", "Normal text with bold and italic mixed"),
        ("The team **dominated** with *precision* plays", "The team dominated with precision plays"),
    ]
    
    print("Testing Markdown Conversion:")
    print("=" * 50)
    all_passed = True
    
    for input_text, expected in test_cases:
        result = clean_markdown_for_docx(input_text)
        passed = result == expected
        status = "✅" if passed else "❌"
        
        if not passed:
            all_passed = False
            
        print(f"{status} Input: '{input_text}'")
        print(f"   Expected: '{expected}'")
        print(f"   Got: '{result}'")
        print()
    
    print("=" * 50)
    if all_passed:
        print("✅ All markdown conversion tests passed!")
    else:
        print("❌ Some tests failed. Check the output above.")
    
    return all_passed

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_markdown_conversion()
    else:
        print("StoryMaker - Gridiron Gazette")
        print("Usage: python storymaker.py test")
        print("\nThis module generates Sabre's witty commentary with markdown cleaning.")