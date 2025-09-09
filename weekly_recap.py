# weekly_recap.py
# Gridiron Gazette — ESPN -> OpenAI recaps -> STYLED Google Doc (no plain MD)
# Requires: OPENAI_API_KEY, LEAGUE_ID, YEAR, GOOGLE_APPLICATION_CREDENTIALS, GDRIVE_DOC_ID
# Optional (private leagues): ESPN_S2, SWID

import os
import pathlib
import datetime as dt
from typing import List, Tuple, Dict, Any

from espn_api.football import League
from openai import OpenAI

from googleapiclient.discovery import build
from google.oauth2 import service_account

from team_mascots import team_mascots

# -------- Env config --------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LEAGUE_ID = int(os.getenv("LEAGUE_ID", "0"))
YEAR = int(os.getenv("YEAR", dt.datetime.now().year))
WEEK_OVERRIDE = os.getenv("WEEK")  # optional override like WEEK=1

# Google / Drive
GDRIVE_DOC_ID = os.getenv("GDRIVE_DOC_ID")  # REQUIRED: we update this Doc
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
    try:
        return team.team_name
    except Exception:
        return f"{getattr(team, 'location', '').strip()} {getattr(team, 'nickname', '').strip()}".strip()


def build_structured(league, week) -> Dict[str, Any]:
    """Return structured data for formatted Google Doc."""
    now_utc = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    title = f"Gridiron Gazette — Week {week}"
    boxes = league.box_scores(week) or []

    quick_hits: List[str] = []
    results_rows: List[List[str]] = [["Home", "Score", "Away", "Score", "Winner"]]
    standings_rows: List[List[str]] = [["#", "Team", "Record", "PF", "PA"]]
    team_sections: List[Tuple[str, str]] = []  # [(team_heading, recap_text)]

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

    # Team recaps
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

    if boxes:
        for b in boxes:
            h_name, a_name = safe_team_name(b.home_team), safe_team_name(b.away_team)
            hs, as_ = round(b.home_score or 0, 2), round(b.away_score or 0, 2)
            h_mascot = team_mascots.get(h_name, "—")
            a_mascot = team_mascots.get(a_name, "—")
            h_recap = recap_for_team(h_name, a_name, hs, as_, h_mascot)
            a_recap = recap_for_team(a_name, h_name, as_, hs, a_mascot)
            team_sections.append((h_name, f"**Mascot:** {h_mascot}\n\n{h_recap}"))
            team_sections.append((a_name, f"**Mascot:** {a_mascot}\n\n{a_recap}"))

    return {
        "title": title,
        "subtitle": f"Generated {now_utc}",
        "quick_hits": quick_hits,
        "results_rows": results_rows,
        "standings_rows": standings_rows,
        "team_sections": team_sections,
        "week": week,
    }


# ---------------- Google Docs writer (styled) ---------------- #

def docs_client():
    scopes = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = service_account.Credentials.from_service_account_file(GOOGLE_CREDS, scopes=scopes)
    return build("docs", "v1", credentials=creds)


def clear_doc_preserving_final_newline(docs, doc_id: str):
    """Delete all content except the final newline (avoid API error)."""
    doc = docs.documents().get(documentId=doc_id).execute()
    body = doc.get("body", {}).get("content", []) or []
    end_index = (body[-1].get("endIndex", 1) if body else 1)
    clear_to = max(1, int(end_index) - 1)
    if clear_to > 1:
        docs.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{"deleteContentRange": {"range": {"startIndex": 1, "endIndex": clear_to}}}]},
        ).execute()


def insert_paragraph(docs, doc_id: str, index: int, text: str, named_style: str = None, bold: bool = False):
    reqs = [{"insertText": {"location": {"index": index}, "text": text + "\n"}}]
    if named_style or bold:
        # Apply paragraph or text styles over the entire inserted paragraph (minus final newline)
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
    docs.documents().batchUpdate(documentId=doc_id, body={"requests": reqs}).execute()
    return index + len(text) + 1  # new cursor


def insert_bullets(docs, doc_id: str, index: int, items: List[str]):
    # Insert all lines, then convert to a bulleted list
    start = index
    for it in items:
        index = insert_paragraph(docs, doc_id, index, it)
    # Apply bullets across the range we just inserted
    docs.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{"createParagraphBullets": {"range": {"startIndex": start, "endIndex": index}, "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"}}]},
    ).execute()
    return index


def insert_table(docs, doc_id: str, index: int, rows: List[List[str]]):
    """Insert a real table and populate cells."""
    if not rows:
        return index
    n_rows = len(rows)
    n_cols = max(len(r) for r in rows)
    # 1) Insert table
    docs.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{"insertTable": {"rows": n_rows, "columns": n_cols, "location": {"index": index}}}]},
    ).execute()
    # After insertion, Google creates the structure at that index; we can target cells by tableStartLocation
    table_start = index
    # 2) Fill cells
    requests = []
    for r, row in enumerate(rows):
        for c, cell_text in enumerate(row):
            if cell_text is None:
                cell_text = ""
            requests.append({
                "insertText": {
                    "text": cell_text,
                    "location": {"index": 0},  # ignored when using tableCellLocation
                    "tableCellLocation": {
                        "tableStartLocation": {"index": table_start},
                        "rowIndex": r,
                        "columnIndex": c
                    }
                }
            })
    docs.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
    # Leave a blank line after table
    return insert_paragraph(docs, doc_id, table_start, "")  # returns next index after blank line


def write_formatted_doc(data: Dict[str, Any]):
    if not GDRIVE_DOC_ID:
        raise SystemExit(
            "GDRIVE_DOC_ID is missing. Create a Doc in Drive, share with the bot as Editor, "
            "add ID as GitHub secret GDRIVE_DOC_ID, and pass it in workflow env."
        )

    docs = docs_client()
    doc_id = GDRIVE_DOC_ID

    # 0) Clear previous content safely
    clear_doc_preserving_final_newline(docs, doc_id)

    # 1) Build the document top->down
    cursor = 1  # start after doc start
    cursor = insert_paragraph(docs, doc_id, cursor, data["title"], named_style="TITLE")
    cursor = insert_paragraph(docs, doc_id, cursor, data["subtitle"], named_style="SUBTITLE")
    cursor = insert_paragraph(docs, doc_id, cursor, "")  # spacer

    # Quick Hits
    if data["quick_hits"]:
        cursor = insert_paragraph(docs, doc_id, cursor, "Quick Hits", named_style="HEADING_2")
        cursor = insert_bullets(docs, doc_id, cursor, data["quick_hits"])
        cursor = insert_paragraph(docs, doc_id, cursor, "")  # spacer

    # Results table
    if data["results_rows"] and len(data["results_rows"]) > 1:
        cursor = insert_paragraph(docs, doc_id, cursor, "This Week’s Results", named_style="HEADING_2")
        cursor = insert_table(docs, doc_id, cursor, data["results_rows"])

    # Standings table
    if data["standings_rows"] and len(data["standings_rows"]) > 1:
        cursor = insert_paragraph(docs, doc_id, cursor, "Standings Snapshot", named_style="HEADING_2")
        cursor = insert_table(docs, doc_id, cursor, data["standings_rows"])

    # Team Recaps
    if data["team_sections"]:
        cursor = insert_paragraph(docs, doc_id, cursor, "Team Recaps", named_style="HEADING_2")
        for team_name, recap_md in data["team_sections"]:
            # Minimal inline cleanup: strip **…** around "Mascot:"
            recap_text = recap_md.replace("**Mascot:**", "Mascot:")
            cursor = insert_paragraph(docs, doc_id, cursor, team_name, named_style="HEADING_3")
            cursor = insert_paragraph(docs, doc_id, cursor, recap_text)
            cursor = insert_paragraph(docs, doc_id, cursor, "")  # spacer

    print("✅ Google Doc updated (styled headings, bullets, and tables).")


# ---------------- Main ---------------- #

def main():
    league = connect_league()
    week = int(WEEK_OVERRIDE) if WEEK_OVERRIDE else getattr(league, "current_week", 1)
    data = build_structured(league, week)

    # also save a text copy locally (optional)
    outdir = pathlib.Path(f"recaps/week_{week}")
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "newsletter.md").write_text(
        f"{data['title']}\n{data['subtitle']}\n\n" + "\n".join(data.get("quick_hits", [])),
        encoding="utf-8",
    )

    write_formatted_doc(data)
    print("✅ Newsletter generated & uploaded.")


if __name__ == "__main__":
    required = [
        "OPENAI_API_KEY",
        "LEAGUE_ID",
        "YEAR",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GDRIVE_DOC_ID",  # required
    ]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise SystemExit(f"Missing required env vars: {missing}. Use GitHub Secrets.")
    main()
