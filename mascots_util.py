# mascots_util.py
# Uses team names from ESPN and maps to your mascot text in team_mascots.py

import re
import unicodedata

try:
    from team_mascots import team_mascots as MASCOTS_RAW  # your existing file
except Exception:
    MASCOTS_RAW = {}

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", (s or "")).strip().lower()
    return re.sub(r"\s+", " ", s)

_MASCOTS_BY_NORM = {}
_MASCOTS_BY_ALNUM = {}

for k, v in MASCOTS_RAW.items():
    nk = _norm(k)
    _MASCOTS_BY_NORM[nk] = v
    _MASCOTS_BY_ALNUM[re.sub(r"[^a-z0-9]", "", nk)] = v

def mascot_for(team_name: str) -> str | None:
    if not team_name:
        return None
    nk = _norm(team_name)
    hit = _MASCOTS_BY_NORM.get(nk)
    if hit:
        return hit
    return _MASCOTS_BY_ALNUM.get(re.sub(r"[^a-z0-9]", "", nk))
