# llm_openai.py
import os
from typing import List, Dict, Optional
from openai import OpenAI

_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

def chat(messages: List[Dict[str, str]],
         model: Optional[str] = None,
         temperature: float = 0.8,
         top_p: float = 0.9,
         max_tokens: int = 900) -> str:
    resp = _client.chat.completions.create(
        model=model or DEFAULT_MODEL,
        messages=messages,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()
