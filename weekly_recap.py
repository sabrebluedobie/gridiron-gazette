# weekly_recap.py
# Gridiron Gazette — ESPN -> OpenAI recaps -> update Google Doc
# Requires: OPENAI_API_KEY, LEAGUE_ID, YEAR, GOOGLE_APPLICATION_CREDENTIALS, GDRIVE_FOLDER_ID, GDRIVE_DOC_ID
# Optional (private leagues): ESPN_S2, SWID

import os
import pathlib
import datetime as dt
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
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID")       # folder where your Doc lives
GDRIVE_DOC_ID = os.getenv("GDRIVE_DOC_ID")             # the Doc to update (required)
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
    """Robust team name getter."""
    try:
        return team.team_name
    except Exception:
        return f"{getattr(team, 'location', '').strip()} {getattr(team, 'nickname', '').strip()}".strip()


def build_standings(league):
    rows = []
    for t in league.teams:
        rows.append((
            safe_team_name(t),
            t.wins,
            t.losses,
            round(t.points_for or 0, 2),
            round(t.points_against or 0, 2),
        ))
    # sort: wins desc, PF desc
    rows.sort(key=lambda x: (-x[1], -x[3]))
    return rows


def md_table(rows):
    """Render a simple Markdown table from a list-of-lists rows (first row is header)."""
    widths = [max(len(str(cell)) for cell in col) for col in zip(*rows)]
    def fmt(r): return "| " + " | ".join(str(c).ljust(w) for c, w in zip(r, widths)) + " |"
    lines = [fmt(rows[0]), "| " + " | ".join("-"*w for w in widths) + " |"]
    for r in rows[1:]:
        lines.append(fmt(r))
    return "\n".join(lines)


def recap_for_team(team_name, opp_name, team_pts, opp_pts, mascot_desc):
    """Generate a short team recap using OpenAI (witty but respectful)."""
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


def build_newsletter(league, week):
    """Assemble the weekly league newsletter in Markdown."""
    lines = []
    lines.append(f"# Gridiron Gazette — Week {week}\n")
    lines.append(f"_Generated {dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_\n")

    # Box scores & quick hits
    boxes = league.box_scores(week)
    if not boxes:
        lines.append("> No box scores available yet for this week.\n")
    else:
        # Highest and closest
        high = max(boxes, key=lambda b: max(b.home_score or 0, b.away_score or 0))
        diffs = [(abs((b.home_score or 0) - (b.away_score or 0)), b) for b in boxes]
        close = min(diffs, key=lambda x: x[0])[1]

        lines.append("## Quick Hits\n")
        lines.append(
            f"- Highest-scoring game: "
            f"{safe_team_name(high.home_team)} {round(high.home_score or 0,2)}–"
            f"{round(high.away_score or 0,2)} {safe_team_name(high.away_team)}"
        )
        lines.append(
            f"- Closest game: "
            f"{safe_team_name(close.home_team)} {round(close.home_score or 0,2)}–"
            f"{round(close.away_score or 0,2)} {safe_team_name(close.away_team)} "
            f"(diff {abs((close.home_score or 0)-(close.away_score or 0)):.2f})\n"
        )

        # Results table
        rows = [["Home", "Score", "Away", "Score", "Winner"]]
        for b in boxes:
            h, a = safe_team_name(b.home_team), safe_team_name(b.away_team)
            hs, as_ = round(b.home_score or 0, 2), round(b.away_score or 0, 2)
            winner = h if hs > as_ else (a if as_ > hs else "Tie")
            rows.append([h, hs, a, as_, winner])
        lines.append("## This Week’s Results\n")
        lines.append(md_table(rows) + "\n")

    # Standings
    standings = build_standings(league)
    srows = [["#", "Team", "Record", "PF", "PA"]]
    for i, (name, w, l, pf, pa) in enumerate(standings, start=1):
        srows.append([i, name, f"{w}-{l}", f"{pf}", f"{pa}"])
    lines.append("## Standings Snapshot\n")
    lines.append(md_table(srows) + "\n")

    # Team recaps
    if boxes:
        lines.append("## Team Recaps\n")
        for b in boxes:
            h_name = safe_team_name(b.home_team)
            a_name = safe_team_name(b.away_team)
            hs, as_ = round(b.home_score or 0, 2), round(b.away_score or 0, 2)

            h_mascot = team_mascots.get(h_name, "—")
            a_mascot = team_mascots.get(a_name, "—")

            h_recap = recap_for_team(h_name, a_name, hs, as_, h_mascot)
            a_recap = recap_for_team(a_name, h_name, as_, hs, a_mascot)

            lines.append(f"### {h_name}\n**Mascot:** {h_mascot}\n\n{h_recap}\n")
            lines.append(f"### {a_name}\n**Mascot:** {a_mascot}\n\n{a_recap}\n")

    return "\n".join(lines)


def upsert_weekly_gdoc(content, week):
    """
    Update an existing Google Doc (requires GDRIVE_DOC_ID).
    Robust approach:
      1) insert content at index 1,
      2) delete everything AFTER the inserted content,
    so we never try to delete the trailing newline at the end of the doc.
    """
    if not GDRIVE_DOC_ID:
        raise SystemExit(
            "GDRIVE_DOC_ID is missing. Create a Doc in your Drive folder, share it with the bot as Editor, "
            "copy the ID from the URL (between /d/ and /edit), add it as a GitHub secret GDRIVE_DOC_ID, "
            "and pass it in the workflow env."
        )

    scopes = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDS, scopes=scopes
    )
    docs = build("docs", "v1", credentials=creds)

    # 1) Insert fresh content at the top
    # NOTE: Google Docs uses UTF-16 code units for indices. Our content is ASCII/UTF-8 Markdown; len() is OK here.
    content_len = len(content)
    docs.documents().batchUpdate(
        documentId=GDRIVE_DOC_ID,
        body={"requests": [
            {"insertText": {"location": {"index": 1}, "text": content}}
        ]},
    ).execute()

    # 2) Delete everything AFTER the inserted content
    # Get updated endIndex after the insert
    doc = docs.documents().get(documentId=GDRIVE_DOC_ID).execute()
    body = doc.get("body", {}).get("content", []) or []
    end_index = (body[-1].get("endIndex", 1) if body else 1)

    # Start deleting right after what we inserted
    delete_start = 1 + content_len
    # Stop before the final newline: subtract 1 to avoid the trailing newline restriction
    delete_end = max(delete_start, int(end_index) - 1)

    if delete_end > delete_start:
        docs.documents().batchUpdate(
            documentId=GDRIVE_DOC_ID,
            body={"requests": [
                {"deleteContentRange": {"range": {"startIndex": delete_start, "endIndex": delete_end}}}
            ]},
        ).execute()

    print("✅ Google Doc updated (insert-then-trim method).")
def main():
    league = connect_league()
    week = int(WEEK_OVERRIDE) if WEEK_OVERRIDE else getattr(league, "current_week", 1)
    content = build_newsletter(league, week)

    outdir = pathlib.Path(f"recaps/week_{week}")
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "newsletter.md").write_text(content, encoding="utf-8")

    upsert_weekly_gdoc(content, week)
    print("✅ Newsletter generated & uploaded.")


if __name__ == "__main__":
    required = [
        "OPENAI_API_KEY",
        "LEAGUE_ID",
        "YEAR",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GDRIVE_FOLDER_ID",
        "GDRIVE_DOC_ID",  # required now
    ]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise SystemExit(f"Missing required env vars: {missing}. Use a local .env (not committed) or GitHub Secrets.")
    main()