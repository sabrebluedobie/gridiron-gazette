#!/usr/bin/env python3
"""
Batch-generate Gridiron Gazette newsletters from a Word template (set-it-and-forget-it),
then optionally upload to Google Drive and email clients a share link + attachment.

SETUP CHECKLIST
1) pip install -r requirements.txt
2) Google Cloud: Enable "Google Drive API" and "Gmail API" for your project.
3) OAuth client (Desktop app) -> download credentials.json to this folder.
4) First run will open a browser to grant access; token.json will be saved for reuse.

RUN
python generate_gazettes.py --upload --email

ENV / CONFIG
- sample_settings.json controls template, input, output, defaults
- Optional per-row overrides: DRIVE_FOLDER_ID, CLIENT_EMAIL
"""

import os
import sys
import csv
import json
import base64
import pathlib
import argparse
from typing import Dict, Any, List

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

# Google APIs
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ---------- SCOPES ----------
DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive.file']
GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.send']

# ---------- CONFIG ----------
CONFIG = {
    "TEMPLATE_PATH": "Gridiron_Gazette_Recap_Template.docx",
    "INPUT_MODE": "csv",                 # "csv" or "json"
    "CSV_PATH": "sample_clients.csv",
    "JSON_PATH": "sample_clients.json",
    "OUTPUT_DIR": "out",
    "DEFAULT_LOGO_PATH": "assets/logo.png",
    "LOGO_WIDTH_MM": 30,
    "WEEK_NUMBER": "",
    # Drive defaults
    "DEFAULT_DRIVE_FOLDER_ID": "",       # If blank, create Week folder under a root chosen on first upload
    # Email defaults
    "DEFAULT_FROM_EMAIL": "",            # If blank, Gmail API uses the authorized account
    "DEFAULT_SUBJECT": "Your Weekly Gridiron Gazette",
    "DEFAULT_MESSAGE": "Hi {{CLIENT_NAME}},\n\nYour Week {{WEEK_NUMBER}} Gazette is ready. Link below and file attached.\n\nThanks!",
}

PLACEHOLDER_KEYS = [
    "WEEK_NUMBER", "WEEKLY_INTRO",
    "MATCHUP1_TEAMS","MATCHUP1_HEADLINE","MATCHUP1_BODY","MATCHUP1_TOP_HOME","MATCHUP1_TOP_AWAY","MATCHUP1_BUST","MATCHUP1_KEYPLAY","MATCHUP1_DEF",
    "MATCHUP2_TEAMS","MATCHUP2_HEADLINE","MATCHUP2_BODY","MATCHUP2_TOP_HOME","MATCHUP2_TOP_AWAY","MATCHUP2_BUST","MATCHUP2_KEYPLAY","MATCHUP2_DEF",
    "MATCHUP3_TEAMS","MATCHUP3_HEADLINE","MATCHUP3_BODY","MATCHUP3_TOP_HOME","MATCHUP3_TOP_AWAY","MATCHUP3_BUST","MATCHUP3_KEYPLAY","MATCHUP3_DEF",
    "MATCHUP4_TEAMS","MATCHUP4_HEADLINE","MATCHUP4_BODY","MATCHUP4_TOP_HOME","MATCHUP4_TOP_AWAY","MATCHUP4_BUST","MATCHUP4_KEYPLAY","MATCHUP4_DEF",
    "MATCHUP5_TEAMS","MATCHUP5_HEADLINE","MATCHUP5_BODY","MATCHUP5_TOP_HOME","MATCHUP5_TOP_AWAY","MATCHUP5_BUST","MATCHUP5_KEYPLAY","MATCHUP5_DEF",
    "MATCHUP6_TEAMS","MATCHUP6_HEADLINE","MATCHUP6_BODY","MATCHUP6_TOP_HOME","MATCHUP6_TOP_AWAY","MATCHUP6_BUST","MATCHUP6_KEYPLAY","MATCHUP6_DEF",
    "AWARD_CUPCAKE_TEAM","AWARD_CUPCAKE_NOTE",
    "AWARD_KITTY_TEAM","AWARD_KITTY_NOTE",
    "AWARD_TOP_TEAM","AWARD_TOP_NOTE",
    "AWARD_PLAY_NOTE","AWARD_MANAGER_NOTE",
    "FOOTER_NOTE",
]

def load_settings(config_path="sample_settings.json"):
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            CONFIG.update(json.load(f))

def load_rows() -> List[Dict[str, Any]]:
    mode = CONFIG["INPUT_MODE"].lower()
    if mode == "csv":
        rows = []
        with open(CONFIG["CSV_PATH"], newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        return rows
    elif mode == "json":
        with open(CONFIG["JSON_PATH"], "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else data.get("rows", [])
    else:
        raise ValueError("INPUT_MODE must be 'csv' or 'json'")

# ---------- Auth Helpers ----------
def get_creds(scopes, token_file, cred_file="credentials.json") -> Credentials:
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(cred_file):
                raise FileNotFoundError(
                    f"Missing {cred_file}. Create OAuth client (Desktop) in Google Cloud and download it here."
                )
            flow = InstalledAppFlow.from_client_secrets_file(cred_file, scopes)
            creds = flow.run_local_server(port=0)
        with open(token_file, 'w', encoding='utf-8') as token:
            token.write(creds.to_json())
    return creds

# ---------- Drive ----------
def ensure_drive_folder(service, name: str, parent_id: str = None) -> str:
    """Return folder ID with given name under parent_id (or root). Create if absent."""
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = service.files().list(q=query, spaces='drive', fields="files(id, name)").execute()
    files = results.get('files', [])
    if files:
        return files[0]['id']
    metadata = {'name': name, 'mimeType': 'application/vnd.google-apps.folder'}
    if parent_id:
        metadata['parents'] = [parent_id]
    folder = service.files().create(body=metadata, fields='id').execute()
    return folder['id']

def upload_to_drive(drive_service, local_path: str, folder_id: str) -> str:
    file_metadata = {'name': os.path.basename(local_path), 'parents': [folder_id]}
    media = MediaFileUpload(local_path, mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document", resumable=True)
    f = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    # Make link accessible to anyone with link (optional; comment out if not desired)
    drive_service.permissions().create(fileId=f['id'], body={'type': 'anyone', 'role': 'reader'}).execute()
    return f['webViewLink']

# ---------- Gmail ----------
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

def create_message_with_attachment(sender, to, subject, message_text, file_path):
    message = MIMEMultipart()
    message['to'] = to
    message['from'] = sender
    message['subject'] = subject

    msg = MIMEText(message_text)
    message.attach(msg)

    with open(file_path, 'rb') as f:
        part = MIMEBase('application', 'vnd.openxmlformats-officedocument.wordprocessingml.document')
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(file_path))
    message.attach(part)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {'raw': raw}

def send_email(gmail_service, sender: str, to: str, subject: str, body: str, attachment_path: str = None):
    if attachment_path:
        message = create_message_with_attachment(sender, to, subject, body, attachment_path)
    else:
        msg = MIMEText(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        message = {'raw': raw}
    sent = gmail_service.users().messages().send(userId='me', body=message).execute()
    return sent.get('id')

# ---------- Rendering ----------
def render_for_row(row: Dict[str, Any]) -> Dict[str, Any]:
    client = row.get("CLIENT_NAME","Client")
    league = row.get("LEAGUE_NAME","League")
    week = CONFIG["WEEK_NUMBER"] or row.get("WEEK_NUMBER","")
    week_label = f"Week-{week}" if week else "Week-X"
    out_dir = os.path.join(CONFIG["OUTPUT_DIR"], league, f"{week_label}")
    os.makedirs(out_dir, exist_ok=True)

    context = {key: row.get(key, "") for key in PLACEHOLDER_KEYS}

    logo_path = row.get("LOGO_PATH") or CONFIG["DEFAULT_LOGO_PATH"]
    tpl = DocxTemplate(CONFIG["TEMPLATE_PATH"])
    if logo_path and os.path.exists(logo_path):
        context["LOGO"] = InlineImage(tpl, logo_path, width=Mm(CONFIG["LOGO_WIDTH_MM"]))
    else:
        context["LOGO"] = ""

    tpl.render(context)

    safe_client = "".join(c for c in client if c.isalnum() or c in (" ","-","_")).strip().replace(" ","_")
    out_name = f"{safe_client}_{week_label}.docx"
    out_path = os.path.join(out_dir, out_name)
    tpl.save(out_path)

    return {
        "client": client,
        "league": league,
        "week": week,
        "output_path": out_path,
        "email": row.get("CLIENT_EMAIL",""),
        "drive_folder_id": row.get("DRIVE_FOLDER_ID",""),
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--upload", action="store_true", help="Upload output docs to Google Drive")
    parser.add_argument("--email", action="store_true", help="Send emails with links/attachments via Gmail API")
    args = parser.parse_args()

    load_settings()
    rows = load_rows()
    if not rows:
        print("No input rows found. Check CSV/JSON.")
        sys.exit(1)

    # Prepare API services if requested
    drive_service = gmail_service = None
    if args.upload:
        drive_creds = get_creds(DRIVE_SCOPES, token_file="token_drive.json")
        drive_service = build('drive', 'v3', credentials=drive_creds)
    if args.email:
        gmail_creds = get_creds(GMAIL_SCOPES, token_file="token_gmail.json")
        gmail_service = build('gmail', 'v1', credentials=gmail_creds)

    created = []
    for row in rows:
        try:
            result = render_for_row(row)
            link = None

            # Upload
            if args.upload and drive_service:
                # Determine target folder: use row override or default
                folder_id = result["drive_folder_id"] or CONFIG["DEFAULT_DRIVE_FOLDER_ID"]
                # If still empty, auto-build a Drive structure: /{League}/Week-{N}
                if not folder_id:
                    league_folder = ensure_drive_folder(drive_service, result["league"])
                    week_folder = ensure_drive_folder(drive_service, f"Week-{result['week'] or 'X'}", parent_id=league_folder)
                    folder_id = week_folder
                link = upload_to_drive(drive_service, result["output_path"], folder_id)

            # Email
            if args.email and gmail_service:
                recipient = result["email"]
                if not recipient:
                    print(f"[WARN] No CLIENT_EMAIL for {result['client']}. Skipping email.")
                else:
                    subject = CONFIG["DEFAULT_SUBJECT"]
                    msg = CONFIG["DEFAULT_MESSAGE"]
                    # simple replace for a couple vars
                    msg = msg.replace("{{CLIENT_NAME}}", result["client"]).replace("{{WEEK_NUMBER}}", str(result["week"] or ""))
                    # include link
                    if link:
                        msg += f"\n\nLink: {link}"
                    sender = CONFIG["DEFAULT_FROM_EMAIL"] or "me"
                    send_email(gmail_service, sender, recipient, subject, msg, attachment_path=result["output_path"])
            created.append(result["output_path"])
            print(f"Created: {result['output_path']}")
        except Exception as e:
            print(f"ERROR for row {row.get('CLIENT_NAME','(unknown)')}: {e}")

    print(f"Done. Generated {len(created)} files.")

if __name__ == "__main__":
    main()
