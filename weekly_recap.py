# weekly_recap.py
# Gridiron Gazette — ESPN -> OpenAI -> styled Google Doc (safe inserts + backoff)

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

from team_mascots import team_mascots as MASCOTS

# -------- Env --------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
LEAGUE_ID = int(os.getenv("LEAGUE_ID", "0"))
YEAR = int(os.getenv("YEAR", dt.datetime.now().year))
WEEK_OVERRIDE = os.getenv("WEEK")

GDRIVE_DOC_ID = os.getenv("GDRIVE_DOC_ID", "").strip()
GOOGLE_CREDS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()

ESPN_S2 = os.getenv("ESPN_S2", "").strip()
SWID = os.getenv("SWID", "").strip()

# -------- Clients --------
client = OpenAI(api_key=OPENAI_API_KEY)


# -------- ESPN helpers --------
def connect_league() -> League:
    if ESPN_S2 and ***REMOVED***
        return League(league_id=LEAGUE_ID, year=YEAR, ***REMOVED***
    return League(league_id=LEAGUE_ID, year=YEAR)


def safe_team_name(team) -> str:
    try:
        return team.team_name
    except Exception:
        loc = getattr(team, "location", "") or ""
        nick = getattr(team, "nickname", "") or ""
        name = (loc + " " + nick).strip()
        return name or "Unknown Team"


def coerce_float(x, default=0.0) -> float:
    try:
        return float(x) if x is not None else float(default)
    except Exception:
        return float(default)


def get_lineup(box, side: str):
    # Try common attributes first
    attrs = ["home_lineup", "home_team_lineup", "homeRoster", "home_roster"] if side == "home" \
            else ["away_lineup", "away_team_lineup", "awayRoster", "away_roster"]
    for a in attrs:
        v = getattr(box, a, None)
        if v:
            return v

    # Fallback to team roster
    team = box.home_team if side == "home" else box.away_team
    roster = getattr(team, "roster", None) or []
    norm = []
    for p in roster:
        class Shim: ...
        s = Shim()
        s.name = getattr(p, "name", "Unknown")
        s.position = getattr(p, "position", "")
        s.points = coerce_float(getattr(p, "points", 0.0))
        s.projected_points = coerce_float(getattr(p, "projected_points", 0.0))
        norm.append(s)
    return norm


# -------- Player summaries --------
def _player_line(p, include_delta=True) -> str:
    name = getattr(p, "name", "Unknown")
    pos = getattr(p, "position", "")
    pts = coerce_float(getattr(p, "points", 0.0))
    proj = coerce_float(getattr(p, "projected_points", 0.0))
    line = f"{name} ({pos}): {pts:.1f}"
    if include_delta:
        delta = pts - proj
        line += f" (proj {proj:.1f}, Δ{delta:+.1f})"
    return line


def summarize_lineup(lineup, top_n=3, under_n=3) -> Tuple[List[str], List[str]]:
    players = []
    for p in lineup or []:
        if not p:
            continue
        pts = coerce_float(getattr(p, "points", 0.0))
        proj = coerce_float(getattr(p, "projected_points", 0.0))
        players.append((p, pts, proj, pts - proj))
    if not players:
        return [], []
    top = [_player_line(x[0]) for x in sorted(players, key=lambda y: y[1], reverse=True)[:top_n]]
    under = [_player_line(x[0]) for x in sorted(players, key=lambda y: y[3])[:under_n]]
    return top, under


# -------- OpenAI recap --------
def team_recap(team_name: str, opp_name: str, team_pts: float, opp_pts: float,
               mascot_desc: str, top_lines: List[str], under_lines: List[str]) -> str:
    if not mascot_desc or mascot_desc == "—":
        mascot_desc = "no mascot set yet"
    sys = (
        "You are the editor of the Gridiron Gazette, writing fun, factual weekly fantasy recaps. "
        "Tone: witty, respectful, PG. 90–130 words. "
        "Use the suggested player bullets to weave 1–2 names naturally."
    )
    outcome = "win" if team_pts > opp_pts else ("loss" if team_pts < opp_pts else "tie")
    bullets_top = "\n- ".join(top_lines) if top_lines else "None"
    bullets_under = "\n- ".join(under_lines) if under_lines else "None"
    user = (
        "Team: {team}\n"
        "Opponent: {opp}\n"
        "Final score: {tp:.1f}–{op:.1f} ({outcome})\n"
        "Mascot persona: {mascot}\n\n"
        "Top performers (suggested):\n- {tops}\n\n"
        "Underperformers (suggested):\n- {unders}\n\n"
        "Write a short recap addressed to {team} fans. Include the final score and one observation that follows from the score "
        "(no invented stats beyond the score). Mention 1–2 players by name from the lists above. "
        "End with 'Next week focus:' and one sentence."
    ).format(team=team_name, opp=opp_name, tp=team_pts, op=opp_pts,
             outcome=outcome, mascot=mascot_desc, tops=bullets_top, unders=bullets_under)

    resp = client.responses.create(
        model="gpt-4o-mini",
        input=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
    )
    return resp.output_text.strip()


# -------- Build newsletter structure --------
def build_structured(league: League, week: int) -> Dict[str, Any]:
    now_utc = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    title = f"Gridiron Gazette — Week {week}"
    boxes = league.box_scores(week) or []

    quick_hits: List[str] = []
    results_rows: List[List[str]] = [["Home", "Score", "Away", "Score", "Winner"]]
    standings_rows: List[List[str]] = [["#", "Team", "Record", "PF", "PA"]]
    team_sections: List[Dict[str, Any]] = []

    if boxes:
        high = max(boxes, key=lambda b: max(b.home_score or 0, b.away_score or 0))
        diffs = [(abs((b.home_score or 0) - (b.away_score or 0)), b) for b in boxes]
        close = min(diffs, key=lambda x: x[0])[1]
        quick_hits.append(
            f"Highest-scoring game: {safe_team_name(high.home_team)} "
            f"{coerce_float(high.home_score):.2f}–{coerce_float(high.away_score):.2f} "
            f"{safe_team_name(high.away_team)}"
        )
        quick_hits.append(
            f"Closest game: {safe_team_name(close.home_team)} "
            f"{coerce_float(close.home_score):.2f}–{coerce_float(close.away_score):.2f} "
            f"{safe_team_name(close.away_team)} "
            f"(diff {abs(coerce_float(close.home_score)-coerce_float(close.away_score)):.2f})"
        )
        for b in boxes:
            h, a = safe_team_name(b.home_team), safe_team_name(b.away_team)
            hs = coerce_float(b.home_score)
            as_ = coerce_float(b.away_score)
            winner = h if hs > as_ else (a if as_ > hs else "Tie")
            results_rows.append([h, f"{hs:.2f}", a, f"{as_:.2f}", winner])

    standings = []
    for t in league.teams:
        standings.append(
            (safe_team_name(t), t.wins, t.losses, coerce_float(t.points_for), coerce_float(t.points_against))
        )
    standings.sort(key=lambda x: (-x[1], -x[3]))
    for i, (name, w, l, pf, pa) in enumerate(standings, start=1):
        standings_rows.append([str(i), name, f"{w}-{l}", f"{pf:.2f}", f"{pa:.2f}"])

    # Per matchup recaps
    if boxes:
        for b in boxes:
            h_name, a_name = safe_team_name(b.home_team), safe_team_name(b.away_team)
            hs, as_ = coerce_float(b.home_score), coerce_float(b.away_score)

            h_top, h_under = summarize_lineup(get_lineup(b, "home"))
            a_top, a_under = summarize_lineup(get_lineup(b, "away"))

            h_m = MASCOTS.get(h_name, "—")
            a_m = MASCOTS.get(a_name, "—")

            h_recap = team_recap(h_name, a_name, hs, as_, h_m, h_top, h_under)
            a_recap = team_recap(a_name, h_name, as_, hs, a_m, a_top, a_under)

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


# -------- Google Docs helpers (append-safe + backoff) --------
def docs_client():
    scopes = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = service_account.Credentials.from_service_account_file(GOOGLE_CREDS, scopes=scopes)
    return build("docs", "v1", credentials=creds)


def docs_call(docs, method: str, **kwargs):
    max_retries = 6
    base = 0.8
    for attempt in range(max_retries):
        try:
            if method == "get":
                return docs.documents().get(**kwargs).execute()
            if method == "batchUpdate":
                resp = docs.documents().batchUpdate(**kwargs).execute()
                time.sleep(0.25)
                return resp
            raise ValueError("Unsupported docs method")
        except HttpError as e:
            status = getattr(e, "status_code", None) or getattr(e.resp, "status", None)
            if status in (429, 500, 502, 503, 504):
                delay = base * (2 ** attempt) + random.uniform(0, 0.4)
                print(f"Docs API {status}; retry in {delay:.2f}s (attempt {attempt+1}/{max_retries})")
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
    idx = start
    for it in items:
        reqs.append({"insertText": {"location": {"index": idx}, "text": it + "\n"}})
        idx += len(it) + 1
    reqs.append({
        "createParagraphBullets": {
            "range": {"startIndex": start, "endIndex": idx},
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
    cell_reqs = []
    for r, row in enumerate(rows):
        for c in range(n_cols):
            text = (row[c] if c < len(row) else "") or ""
            cell_reqs.append({
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
    if cell_reqs:
        docs_call(docs, "batchUpdate", documentId=doc_id, body={"requests": cell_reqs})
    insert_paragraph(docs, doc_id, "")  # spacer


def write_formatted_doc(data: Dict[str, Any]):
    if not GDRIVE_DOC_ID:
        raise SystemExit(
            "GDRIVE_DOC_ID missing. Create a Doc, share with the service account as Editor, set secret GDRIVE_DOC_ID."
        )
    docs = docs_client()
    doc_id = GDRIVE_DOC_ID

    clear_doc_preserving_final_newline(docs, doc_id)

    insert_paragraph(docs, doc_id, data["title"], named_style="TITLE")
    insert_paragraph(docs, doc_id, data["subtitle"], named_style="SUBTITLE")
    insert_paragraph(docs, doc_id, "")

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
            if sec["top"]:
                insert_paragraph(docs, doc_id, "Top performers", named_style="HEADING_4")
                insert_bullets(docs, doc_id, sec["top"])
            if sec["under"]:
                insert_paragraph(docs, doc_id, "Underperformers", named_style="HEADING_4")
                insert_bullets(docs, doc_id, sec["under"])
            insert_paragraph(docs, doc_id, "")

    print("Doc updated successfully.")


# -------- Main --------
def main():
    required = ["OPENAI_API_KEY", "LEAGUE_ID", "YEAR", "GOOGLE_APPLICATION_CREDENTIALS", "GDRIVE_DOC_ID"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise SystemExit(f"Missing required env vars: {missing}")

    league = connect_league()
    week = int(WEEK_OVERRIDE) if WEEK_OVERRIDE else getattr(league, "current_week", 1)
    data = build_structured(league, week)

    # Optional local artifact
    outdir = pathlib.Path(f"recaps/week_{week}")
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "newsletter.md").write_text(
        f"{data['title']}\n{data['subtitle']}\n", encoding="utf-8"
    )

    write_formatted_doc(data)
    print("✅ Newsletter generated & uploaded.")


if __name__ == "__main__":
    main()