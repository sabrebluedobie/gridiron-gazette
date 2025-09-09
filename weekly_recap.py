# weekly_recap.py
# Gridiron Gazette — ESPN -> OpenAI recaps -> STYLED Google Doc (append-safe + backoff)
#
# Requires GitHub Secrets/env:
#   OPENAI_API_KEY, LEAGUE_ID, YEAR, GOOGLE_APPLICATION_CREDENTIALS, GDRIVE_DOC_ID
# Optional (private leagues):
#   ESPN_S2, SWID
#
# The Google Doc with id GDRIVE_DOC_ID must be shared with your service account as Editor.

import os
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

from team_mascots import team_mascots

# -------- Env config --------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LEAGUE_ID = int(os.getenv("LEAGUE_ID", "0"))
YEAR = int(os.getenv("YEAR", dt.datetime.now().year))
WEEK_OVERRIDE = os.getenv("WEEK")  # optional override like WEEK=2

# Google / Drive
GDRIVE_DOC_ID = os.getenv("GDRIVE_DOC_ID")  # REQUIRED: update this Doc
GOOGLE_CREDS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# ESPN cookies (only if league is private)
ESPN_S2 = os.getenv("ESPN_S2")
SWID = os.getenv("SWID")

# -------- Clients --------
client = OpenAI(api_key=OPENAI_API_KEY)


def connect_league():
    """Connect to ESPN league (with cookies if private)."""
    if ESPN_S2 and ***REMOVED***
        return League(league_id=LEAGUE_ID, year=YEAR, ***REMOVED***
    return League(league_id=LEAGUE_ID, year=YEAR)


def safe_team_name(team):
    """Robust team name getter with fallback."""
    try:
        return team.team_name
    except Exception:
        return f"{getattr(team, 'location', '').strip()} {getattr(team, 'nickname', '').strip()}".strip()


# ---------------- Player helpers ---------------- #

def _player_line(p, include_delta: bool = True) -> str:
    """Format a player as 'Name (POS): pts (proj X, ΔY)' with safe fallbacks."""
    name = getattr(p, "name", "Unknown")
    pos = getattr(p, "position", "")
    pts = getattr(p, "points", 0.0) or 0.0
    proj = getattr(p, "projected_points", None)
    if proj is None:
        # Some ESPN weeks don’t return projections for all lineups
        proj = 0.0
        include_delta = False
    line = f"{name} ({pos}): {pts:.1f}"
    if include_delta:
        delta = pts - proj
        line += f" (proj {proj:.1f}, Δ{delta:+.1f})"
    return line


def summarize_lineup(lineup, top_n=3, under_n=3):
    """
    Return (top, under) lists of strings:
      - top: highest points
      - under: worst delta (actual - projected)
    """
    players = []
    for p in lineup or []:
        # Filter out empty slots / None
        if not p:
            continue
        pts = getattr(p, "points", 0.0) or 0.0
        proj = getattr(p, "projected_points", 0.0) or 0.0
        delta = pts - proj
        players.append((p, pts, proj, delta))

    if not players:
        return [], []

    # Top by raw points
    top_sorted = sorted(players, key=lambda x: x[1], reverse=True)[:top_n]
    top = [_player_line(p, include_delta=True) for (p, _, __, ___) in top_sorted]

    # Underperformers by delta (most negative)
    under_sorted = sorted(players, key=lambda x: x[3])[:under_n]
    under = [_player_line(p, include_delta=True) for (p, _, __, ___) in under_sorted]

    return top, under


# ---------------- Build structured newsletter data ---------------- #

def build_structured(league, week) -> Dict[str, Any]:
    """Return structured data for formatted Google Doc."""
    now_utc = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    title = f"Gridiron Gazette — Week {week}"
    boxes = league.box_scores(week) or []

    quick_hits: List[str] = []
    results_rows: List[List[str]] = [["Home", "Score", "Away", "Score", "Winner"]]
    standings_rows: List[List[str]] = [["#", "Team", "Record", "PF", "PA"]]
    team_sections: List[Dict[str, Any]] = []  # [{team, recap, top, under}]

    # Quick hits + results
    if boxes:
        high = max(boxes, key=lambda b: max(b.home_score or 0, b.away_score or 0))
        diffs = [(abs((b.home_score or 0) - (b.away_score or 0)), b) for b in boxes]
        close = min(diffs, key=lambda x: x[0])[1]

        quick_hits.append(
            f"Highest-scoring game: {safe_team_name(high.home_team)} "
            f"{round(high.home_score or 0,2)}–{round(high.away_score or 0,2)} "
            f"{safe_team_name(high.away_team)}"
        )
        quick_hits.append(
            f"Closest game: {safe_team_name(close.home_team)} "
            f"{round(close.home_score or 0,2)}–{round(close.away_score or 0,2)} "
            f"{safe_team_name(close.away_team)} "
            f"(diff {abs((close.home_score or 0)-(close.away_score or 0)):.2f})"
        )

        for b in boxes:
            h, a = safe_team_name(b.home_team), safe_team_name(b.away_team)
            hs, as_ = round(b.home_score or 0, 2), round(b.away_score or 0, 2)
            winner = h if hs > as_ else (a if as_ > hs else "Tie")
            results_rows.append([h, str(hs), a, str(as_), winner])

    # Standings
    standings = []
    for t in league.teams:
        standings.append(
            (safe_team_name(t), t.wins, t.losses, round(t.points_for or 0, 2), round(t.points_against or 0, 2))
        )
    standings.sort(key=lambda x: (-x[1], -x[3]))
    for i, (name, w, l, pf, pa) in enumerate(standings, start=1):
        standings_rows.append([str(i), name, f"{w}-{l}", f"{pf}", f"{pa}"])

    # Team recaps (OpenAI) + player lists
    def recap_for_team(team_name, opp_name, team_pts, opp_pts, mascot_desc, top_lines, under_lines):
        # If mascot missing, make it explicit (so you can spot it and fill the file)
        if not mascot_desc or mascot_desc == "—":
            mascot_desc = "no mascot set yet"

        system = (
            "You are the editor of the Gridiron Gazette, writing fun, factual weekly fantasy recaps. "
            "Tone: witty but respectful; 90–130 words; PG language. "
            "Use the player bullet suggestions to weave 1–2 names naturally into the recap."
        )
        user = f"""
Team: {team_name}
Opponent: {opp_name}
Final score: {team_pts}–{opp_pts} ({'win' if team_pts>opp_pts else ('loss' if team_pts<opp_pts else 'tie')})
Mascot persona: {mascot_desc}

Top performers (suggested to reference):
- {("\n- ".join(top_lines)) if top_lines else "None available"}

Underperformers (do not roast, just light accountability):
- {("\n- ".join(under_lines)) if under_lines else "None available"}

Write a short recap addressed to {team_name} fans. Include the final score and one observation that follows from the score (no invented stats beyond the score). Mention 2-3 players by name from the lists above. End with "Next week focus:" and one sentence.
cleaned_text = some_text.strip()
f"{cleaned_text}"

        resp = client.responses.create(
            model="gpt-4o-mini",
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.output_text.strip()

    if boxes:
        for b in boxes:
            h_name, a_name = safe_team_name(b.home_team), safe_team_name(b.away_team)
            hs, as_ = round(b.home_score or 0, 2), round(b.away_score or 0, 2)

            # Lineups: home then away (espn_api exposes .home_lineup / .away_lineup on box score)
            h_top, h_under = summarize_lineup(getattr(b, "home_lineup", []))
            a_top, a_under = summarize_lineup(getattr(b, "away_lineup", []))

            h_mascot = team_mascots.get(h_name, "—")
            a_mascot = team_mascots.get(a_name, "—")

            h_recap = recap_for_team(h_name, a_name, hs, as_, h_mascot, h_top, h_under)
            a_recap = recap_for_team(a_name, h_name, as_, hs, a_mascot, a_top, a_under)

            team_sections.append({"team": h_name, "recap": h_recap, "top": h_top, "under": h_under})
            team_sections.append({"team": a_name, "recap": a_recap, "top": a_top, "under": a_under})

    return {
        "title": title,
        "subtitle": f"Generated {now_utc}",
        "quick_hits": quick_hits,
        "results_rows": results_rows,
        "standings_rows": standings_rows,
        "team_sections": team_sections,
        "week": week,
    }


# ---------------- Google Docs helpers (append-safe + backoff) ---------------- #

def docs_client():
    scopes = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = service_account.Credentials.from_service_account_file(GOOGLE_CREDS, scopes=scopes)
    return build("docs", "v1", credentials=creds)


def docs_call(docs, method: str, **kwargs):
    """Retry/backoff wrapper for Docs API calls."""
    max_retries = 6
    base = 0.8
    for attempt in range(max_retries):
        try:
            if method == "get":
                return docs.documents().get(**kwargs).execute()
            elif method == "batchUpdate":
                resp = docs.documents().batchUpdate(**kwargs).execute()
                time.sleep(0.25)  # soft pacing
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


def write_formatted_doc(data: Dict[str, Any]):
    """Build a fully-styled Google Doc for the week."""
    if not GDRIVE_DOC_ID:
        raise SystemExit(
            "GDRIVE_DOC_ID is missing. Create a Doc in Drive, share with the bot as Editor, "
            "add ID as GitHub secret GDRIVE_DOC_ID, and pass it in workflow env."
        )

    docs = docs_client()
    doc_id = GDRIVE_DOC_ID

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
        for sec in data["team_sections"]:
            insert_paragraph(docs, doc_id, sec["team"], named_style="HEADING_3")
            insert_paragraph(docs, doc_id, sec["recap"])
            # Add player bullets right under the recap
            if sec["top"]:
                insert_paragraph(docs, doc_id, "Top performers", named_style="HEADING_4")
                insert_bullets(docs, doc_id, sec["top"])
            if sec["under"]:
                insert_paragraph(docs, doc_id, "Underperformers", named_style="HEADING_4")
                insert_bullets(docs, doc_id, sec["under"])
            insert_paragraph(docs, doc_id, "")  # spacer

    print("✅ Google Doc updated (styled headings, bullets, tables, and player sections).")


# ---------------- Main ---------------- #

def main():
    league = connect_league()
    week = int(WEEK_OVERRIDE) if WEEK_OVERRIDE else getattr(league, "current_week", 1)
    data = build_structured(league, week)

    # also save a text copy locally (optional artifact)
    outdir = pathlib.Path(f"recaps/week_{week}")
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "newsletter.md").write_text(
        f"{data['title']}\n{data['subtitle']}\n", encoding="utf-8"
    )

    write_formatted_doc(data)
    print("✅ Newsletter generated & uploaded.")


if __name__ == "__main__":
    required = [
        "OPENAI_API_KEY",
        "LEAGUE_ID",
        "YEAR",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GDRIVE_DOC_ID",
    ]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise SystemExit(f"Missing required env vars: {missing}. Use GitHub Secrets.")
    main()