# weekly_recap_multi.py
# Run weekly for MANY leagues:
# - reads leagues.json
# - pulls ESPN data (per league)
# - generates OpenAI recaps (per team)
# - writes a STYLED Google Doc (per league) with retries & safe indices
#
# Env/Secrets required (repo-level):
#   OPENAI_API_KEY
#   GOOGLE_APPLICATION_CREDENTIALS (path to creds.json written by workflow)
#
# Per-league:
#   league_id, year, gdoc_id in leagues.json
#   Optional: espn_s2, swid (for private leagues)
#
# Files:
#   leagues.json  (array of league configs)
#   team_mascots.py  (global defaults; config may override per league)

import os
import json
import time
import random
import pathlib
import datetime as dt
from typing import List, Tuple, Dict, Any

from espn_api.football import League
from openai import OpenAI

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account

from team_mascots import team_mascots as default_mascots

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_CREDS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# OpenAI client (one per run)
client = OpenAI(api_key=OPENAI_API_KEY)


# ---------------- ESPN helpers ---------------- #

def connect_league(league_id: int, year: int, ***REMOVED***
    """Connect to ESPN league (with cookies if private)."""
    if espn_s2 and ***REMOVED***
        return League(league_id=league_id, year=year, ***REMOVED***
    return League(league_id=league_id, year=year)


def safe_team_name(team):
    try:
        return team.team_name
    except Exception:
        return f"{getattr(team, 'location', '').strip()} {getattr(team, 'nickname', '').strip()}".strip()


# ---------------- Google Docs helpers (append-safe writer + backoff) ---------------- #

def docs_client():
    scopes = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = service_account.Credentials.from_service_account_file(GOOGLE_CREDS_PATH, scopes=scopes)
    return build("docs", "v1", credentials=creds)


def docs_call(docs, method: str, **kwargs):
    """Wrapper with retry/backoff for batchUpdate-heavy calls."""
    max_retries = 6
    base = 0.8
    for attempt in range(max_retries):
        try:
            if method == "get":
                return docs.documents().get(**kwargs).execute()
            elif method == "batchUpdate":
                resp = docs.documents().batchUpdate(**kwargs).execute()
                time.sleep(0.25)  # gentle pacing
                return resp
            else:
                raise ValueError("Unsupported docs method")
        except HttpError as e:
            status = getattr(e, "status_code", None) or getattr(e.resp, "status", None)
            if status in (429, 500, 502, 503, 504):
                delay = base * (2 ** attempt) + random.uniform(0, 0.4)
                print(f"⚠️ Docs API {status} — retry in {delay:.2f}s (attempt {attempt+1}/{max_retries})")
                time.sleep(delay)
                continue
            raise


def _end_insert_index(docs, doc_id: str) -> int:
    doc = docs_call(docs, "get", documentId=doc_id)
    body = doc.get("body", {}).get("content", []) or []
    end_index = (body[-1].get("endIndex", 1) if body else 1)
    return max(1, int(end_index) - 1)


def clear_doc_preserving_final_newline(docs, doc_id: str):
    doc = docs_call(docs, "get", documentId=doc_id)
    body = doc.get("body", {}).get("content", []) or []
    end_index = (body[-1].get("endIndex", 1) if body else 1)
    clear_to = max(1, int(end_index) - 1)
    if clear_to > 1:
        docs_call(
            docs, "batchUpdate",
            documentId=doc_id,
            body={"requests": [{"deleteContentRange": {"range": {"startIndex": 1, "endIndex": clear_to}}}]},
        )


def insert_paragraph(docs, doc_id: str, text: str, named_style: str = None, bold: bool = False):
    index = _end_insert_index(docs, doc_id)
    reqs = [{"insertText": {"location": {"index": index}, "text": text + "\n"}}]
    if named_style or bold:
        length = len(text)
        if named_style:
            reqs.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": index, "endIndex": index + length + 1},
                    "paragraphStyle": {"namedStyleType": named_style},
                    "fields": "namedStyleType"
                }
            })
        if bold and length > 0:
            reqs.append({
                "updateTextStyle": {
                    "range": {"startIndex": index, "endIndex": index + length},
                    "textStyle": {"bold": True},
                    "fields": "bold"
                }
            })
    docs_call(docs, "batchUpdate", documentId=doc_id, body={"requests": reqs})


def insert_bullets(docs, doc_id: str, items: List[str]):
    start = _end_insert_index(docs, doc_id)
    reqs = []
    running_index = start
    for it in items:
        reqs.append({"insertText": {"location": {"index": running_index}, "text": it + "\n"}})
        running_index += len(it) + 1
    reqs.append({
        "createParagraphBullets": {
            "range": {"startIndex": start, "endIndex": running_index},
            "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"
        }
    })
    docs_call(docs, "batchUpdate", documentId=doc_id, body={"requests": reqs})


def insert_table(docs, doc_id: str, rows: List[List[str]]):
    if not rows:
        return
    n_rows = len(rows)
    n_cols = max(len(r) for r in rows)
    table_start = _end_insert_index(docs, doc_id)
    docs_call(
        docs, "batchUpdate",
        documentId=doc_id,
        body={"requests": [{"insertTable": {"rows": n_rows, "columns": n_cols, "location": {"index": table_start}}}]},
    )
    reqs = []
    for r, row in enumerate(rows):
        for c in range(n_cols):
            text = (row[c] if c < len(row) else "") or ""
            reqs.append({
                "insertText": {
                    "text": text,
                    "location": {"index": 0},
                    "tableCellLocation": {
                        "tableStartLocation": {"index": table_start},
                        "rowIndex": r,
                        "columnIndex": c
                    }
                }
            })
    if reqs:
        docs_call(docs, "batchUpdate", documentId=doc_id, body={"requests": reqs})
    insert_paragraph(docs, doc_id, "")  # spacer


# ---------------- Newsletter builder per league ---------------- #

def build_structured(league, week, league_mascots: Dict[str, str]) -> Dict[str, Any]:
    now_utc = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    title = f"Gridiron Gazette — Week {week}"
    boxes = league.box_scores(week) or []

    quick_hits: List[str] = []
    results_rows: List[List[str]] = [["Home", "Score", "Away", "Score", "Winner"]]
    standings_rows: List[List[str]] = [["#", "Team", "Record", "PF", "PA"]]
    team_sections: List[Tuple[str, str]] = []

    if boxes:
        high = max(boxes, key=lambda b: max(b.home_score or 0, b.away_score or 0))
        diffs = [(abs((b.home_score or 0) - (b.away_score or 0)), b) for b in boxes]
        close = min(diffs, key=lambda x: x[0])[1]

        quick_hits.append(
            f"Highest-scoring game: {safe_team_name(high.home_team)} "
            f"{round(high.home_score or 0,2)}–{round(high.away_score or 0,2)} {safe_team_name(high.away_team)}"
        )
        quick_hits.append(
            f"Closest game: {safe_team_name(close.home_team)} "
            f"{round(close.home_score or 0,2)}–{round(close.away_score or 0,2)} {safe_team_name(close.away_team)} "
            f"(diff {abs((close.home_score or 0)-(close.away_score or 0)):.2f})"
        )

        for b in boxes:
            h, a = safe_team_name(b.home_team), safe_team_name(b.away_team)
            hs, as_ = round(b.home_score or 0, 2), round(b.away_score or 0, 2)
            winner = h if hs > as_ else (a if as_ > hs else "Tie")
            results_rows.append([h, str(hs), a, str(as_), winner])

    standings = []
    for t in league.teams:
        standings.append(
            (safe_team_name(t), t.wins, t.losses, round(t.points_for or 0, 2), round(t.points_against or 0, 2))
        )
    standings.sort(key=lambda x: (-x[1], -x[3]))
    for i, (name, w, l, pf, pa) in enumerate(standings, start=1):
        standings_rows.append([str(i), name, f"{w}-{l}", f"{pf}", f"{pa}"])

    def recap_for_team(team_name, opp_name, team_pts, opp_pts, mascot_desc):
        system = (
            "You write fun, factual weekly fantasy football recaps. "
            "Tone: witty but respectful; 90–130 words; PG language."
        )
        user = f"""
Team: {team_name}
Opponent: {opp_name}
Final score: {team_pts}–{opp_pts} ({'win' if team_pts>opp_pts else ('loss' if team_pts<opp_pts else 'tie')})
Mascot persona: {mascot_desc}

Write a short recap addressed to {team_name} fans. Include the final score and one observation that follows from the score (no invented stats beyond the score). End with "Next week focus:" and one sentence.
""".strip()

        resp = client.responses.create(
            model="gpt-4o-mini",
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.output_text.strip()

    boxes = league.box_scores(week) or []
    if boxes:
        for b in boxes:
            h_name, a_name = safe_team_name(b.home_team), safe_team_name(b.away_team)
            hs, as_ = round(b.home_score or 0, 2), round(b.away_score or 0, 2)
            h_m = league_mascots.get(h_name, default_mascots.get(h_name, "—"))
            a_m = league_mascots.get(a_name, default_mascots.get(a_name, "—"))
            h_recap = recap_for_team(h_name, a_name, hs, as_, h_m)
            a_recap = recap_for_team(a_name, h_name, as_, hs, a_m)
            team_sections.append((h_name, f"Mascot: {h_m}\n\n{h_recap}"))
            team_sections.append((a_name, f"Mascot: {a_m}\n\n{a_recap}"))

    return {
        "title": title,
        "subtitle": f"Generated {now_utc}",
        "quick_hits": quick_hits,
        "results_rows": results_rows,
        "standings_rows": standings_rows,
        "team_sections": team_sections,
    }


def write_formatted_doc(doc_id: str, data: Dict[str, Any]):
    docs = docs_client()
    clear_doc_preserving_final_newline(docs, doc_id)

    insert_paragraph(docs, doc_id, data["title"], named_style="TITLE")
    insert_paragraph(docs, doc_id, data["subtitle"], named_style="SUBTITLE")
    insert_paragraph(docs, doc_id, "")  # spacer

    if data["quick_hits"]:
        insert_paragraph(docs, doc_id, "Quick Hits", named_style="HEADING_2")
        insert_bullets(docs, doc_id, data["quick_hits"])
        insert_paragraph(docs, doc_id, "")

    if data["results_rows"] and len(data["results_rows"]) > 1:
        insert_paragraph(docs, doc_id, "This Week’s Results", named_style="HEADING_2")
        try:
            insert_table(docs, doc_id, data["results_rows"])
        except HttpError:
            insert_paragraph(docs, doc_id, "(table unavailable — fallback)")
            for row in data["results_rows"]:
                insert_paragraph(docs, doc_id, "   ".join(row))
            insert_paragraph(docs, doc_id, "")

    if data["standings_rows"] and len(data["standings_rows"]) > 1:
        insert_paragraph(docs, doc_id, "Standings Snapshot", named_style="HEADING_2")
        try:
            insert_table(docs, doc_id, data["standings_rows"])
        except HttpError:
            insert_paragraph(docs, doc_id, "(table unavailable — fallback)")
            for row in data["standings_rows"]:
                insert_paragraph(docs, doc_id, "   ".join(row))
            insert_paragraph(docs, doc_id, "")

    if data["team_sections"]:
        insert_paragraph(docs, doc_id, "Team Recaps", named_style="HEADING_2")
        for team_name, recap_text in data["team_sections"]:
            insert_paragraph(docs, doc_id, team_name, named_style="HEADING_3")
            insert_paragraph(docs, doc_id, recap_text)
            insert_paragraph(docs, doc_id, "")


def run_for_league(cfg: Dict[str, Any], week_override: int = None):
    name = cfg.get("name", f"League {cfg['league_id']}")
    league_id = int(cfg["league_id"])
    year = int(cfg.get("year", dt.datetime.now().year))
    gdoc_id = cfg["gdoc_id"]
    espn_s2 = cfg.get("espn_s2", "")
    swid = cfg.get("swid", "")
    mascots = cfg.get("mascots", {})

    print(f"🔹 Processing: {name} (ID {league_id})")
    league = connect_league(league_id, year, espn_s2, swid)
    week = int(week_override) if week_override else getattr(league, "current_week", 1)
    data = build_structured(league, week, mascots)

    # optional artifact per league
    outdir = pathlib.Path(f"recaps/{league_id}/week_{week}")
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "newsletter.md").write_text(
        f"{data['title']}\n{data['subtitle']}\n", encoding="utf-8"
    )

    write_formatted_doc(gdoc_id, data)
    print(f"✅ Updated Google Doc for {name}")


def main():
    leagues_path = pathlib.Path("leagues.json")
    if not leagues_path.exists():
        raise SystemExit("leagues.json not found in repo root.")
    leagues = json.loads(leagues_path.read_text(encoding="utf-8"))
    week_override = os.getenv("WEEK")

    # sanity checks
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Missing OPENAI_API_KEY")
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        raise SystemExit("Missing GOOGLE_APPLICATION_CREDENTIALS (path to creds.json)")

    for cfg in leagues:
        try:
            run_for_league(cfg, week_override=week_override)
        except Exception as e:
            print(f"❌ League {cfg.get('name', cfg.get('league_id'))} failed: {e}")


if __name__ == "__main__":
    main()