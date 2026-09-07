#!/usr/bin/env python3
"""Morning Gmail summary.

Fetches emails from the last N hours, filters out the noise
(promotions, social, newsletters, account notifications), summarizes
what remains (sender + subject + 1-2 lines), and emails the digest to you.

LinkedIn job offers get their own section. The "interesting to me" logic
is a placeholder for now -- to be refined together.

First run opens a browser for one-time Google authorization, then stores
token.json for unattended runs.
"""

import base64
import html
import json
import os
import re
import sys
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"
CONFIG_FILE = BASE_DIR / "config.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

DEFAULT_CONFIG = {
    "send_to": "me",
    "lookback_hours": 24,
    "exclude_categories": ["promotions", "social"],
    "exclude_newsletters": True,
    "account_notification_keywords": [
        "security alert",
        "new sign-in",
        "new sign in",
        "sign-in attempt",
        "sign in attempt",
        "password reset",
        "password changed",
        "verify your",
        "verification code",
        "login alert",
        "log in alert",
        "two-factor",
        "2-step verification",
        "account activity",
    ],
    "linkedin": {
        "enabled": True,
        "job_offer_keywords": ["job alert", "jobs for you", "new jobs", "job opportunity"],
    },
    "summary_max_chars": 280,
    "max_emails": 50,
}


# ---------------------------------------------------------------- config

def load_config():
    if CONFIG_FILE.exists():
        cfg = json.loads(CONFIG_FILE.read_text())
    else:
        cfg = {}
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    linkedin = dict(DEFAULT_CONFIG["linkedin"])
    linkedin.update(cfg.get("linkedin", {}))
    merged["linkedin"] = linkedin
    return merged


# ---------------------------------------------------------------- auth

def get_service():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                sys.exit(
                    f"Missing {CREDENTIALS_FILE}.\n"
                    "Follow README.md to create Google Cloud credentials first."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


# ---------------------------------------------------------------- fetch

def list_messages(service, query, max_results):
    resp = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    return resp.get("messages", [])


def get_message(service, msg_id):
    return (
        service.users()
        .messages()
        .get(userId="me", id=msg_id, format="full")
        .execute()
    )


def header(msg, name):
    for h in msg.get("payload", {}).get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def sender_name(raw_from):
    """'Jane Doe <jane@x.com>' -> 'Jane Doe (jane@x.com)'"""
    m = re.match(r'^\s*"?([^"<]*)"?\s*<([^>]+)>', raw_from or "")
    if m:
        name, addr = m.group(1).strip(), m.group(2).strip()
        return f"{name} ({addr})" if name else addr
    return (raw_from or "").strip() or "Unknown sender"


# ---------------------------------------------------------------- body / summary

def decode_part(part):
    data = part.get("body", {}).get("data")
    if not data:
        return ""
    raw = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    return raw


def extract_body(payload):
    """Prefer text/plain, fall back to stripped text/html."""
    plain, html_body = "", ""
    stack = [payload]
    while stack:
        part = stack.pop()
        mime = part.get("mimeType", "")
        if mime == "text/plain" and not plain:
            plain = decode_part(part)
        elif mime == "text/html" and not html_body:
            html_body = decode_part(part)
        stack.extend(part.get("parts", []))
    if plain.strip():
        return plain
    return strip_html(html_body)


def strip_html(text):
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return html.unescape(text)


def clean_body(text):
    """Drop quoted replies and common signature noise."""
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(">"):
            continue
        if re.match(r"^On .{0,120}wrote:$", s):
            break
        if s in ("--", "-- ", "—", "–"):
            break
        lines.append(s)
    text = " ".join(lines)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def summarize(body, snippet, max_chars):
    """Extractive 1-2 line summary from the body, falling back to Gmail's snippet."""
    source = body if len(body) > 40 else (snippet or body)
    if not source:
        return "(no preview available)"
    sentences = re.split(r"(?<=[.!?])\s+", source)
    out = ""
    for s in sentences:
        candidate = (out + " " + s).strip()
        if len(candidate) > max_chars:
            break
        out = candidate
        if out.count(".") + out.count("!") + out.count("?") >= 2:
            break
    if not out:
        out = source[:max_chars]
    if len(out) >= max_chars:
        out = out[: max_chars - 1].rstrip() + "…"
    return out


# ---------------------------------------------------------------- filtering

def is_newsletter(msg):
    return bool(header(msg, "List-Unsubscribe"))


def is_account_notification(msg, keywords):
    haystack = f"{header(msg, 'Subject')}\n{msg.get('snippet', '')}".lower()
    return any(k.lower() in haystack for k in keywords)


def is_linkedin(msg):
    return "linkedin.com" in header(msg, "From").lower()


def is_job_offer(msg, keywords):
    haystack = f"{header(msg, 'Subject')}\n{msg.get('snippet', '')}".lower()
    return any(k.lower() in haystack for k in keywords)


def is_interesting_job_offer(msg):
    """PLACEHOLDER -- to be refined together.

    For now every LinkedIn job-offer email counts as interesting, so the
    summary section stays visible while we define what 'interesting'
    means (titles, companies, locations, salary, etc.).
    """
    return True


# ---------------------------------------------------------------- digest

def build_digest(service, cfg):
    hours = cfg["lookback_hours"]
    max_emails = cfg["max_emails"]
    categories = " ".join(f"-category:{c}" for c in cfg["exclude_categories"])
    query = f"newer_than:{hours}h {categories}"

    kept, linkedin_jobs = [], []
    for stub in list_messages(service, query, max_emails):
        msg = get_message(service, stub["id"])
        if "SENT" in msg.get("labelIds", []):
            continue
        if cfg["linkedin"]["enabled"] and is_linkedin(msg):
            if is_job_offer(msg, cfg["linkedin"]["job_offer_keywords"]):
                linkedin_jobs.append(msg)
            continue
        if cfg["exclude_newsletters"] and is_newsletter(msg):
            continue
        if is_account_notification(msg, cfg["account_notification_keywords"]):
            continue
        body = clean_body(extract_body(msg.get("payload", {})))
        kept.append(
            {
                "sender": sender_name(header(msg, "From")),
                "subject": header(msg, "Subject") or "(no subject)",
                "summary": summarize(body, msg.get("snippet", ""), cfg["summary_max_chars"]),
            }
        )

    interesting_jobs = [m for m in linkedin_jobs if is_interesting_job_offer(m)]
    return kept, interesting_jobs


def render_digest(kept, interesting_jobs):
    lines = [f"Morning email summary — {len(kept)} email(s) worth your attention.", ""]
    if kept:
        for i, e in enumerate(kept, 1):
            lines.append(f"{i}. From: {e['sender']}")
            lines.append(f"   Subject: {e['subject']}")
            lines.append(f"   {e['summary']}")
            lines.append("")
    else:
        lines.append("Nothing needs your attention this morning. 🎉")
        lines.append("")

    if interesting_jobs:
        lines.append(f"💼 {len(interesting_jobs)} potentially interesting LinkedIn job offer(s):")
        for m in interesting_jobs:
            lines.append(f"   - {header(m, 'Subject')}")
        lines.append("")

    lines.append("— sent by gmail-morning-summary")
    return "\n".join(lines)


# ---------------------------------------------------------------- send

def send_summary(service, cfg, body_text):
    if cfg["send_to"] == "me":
        profile = service.users().getProfile(userId="me").execute()
        to_addr = profile["emailAddress"]
    else:
        to_addr = cfg["send_to"]
    msg = MIMEText(body_text, "plain", "utf-8")
    msg["to"] = to_addr
    msg["subject"] = "☀️ Your morning email summary"
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"Summary sent to {to_addr}")


# ---------------------------------------------------------------- main

def main():
    cfg = load_config()
    service = get_service()
    kept, interesting_jobs = build_digest(service, cfg)
    digest = render_digest(kept, interesting_jobs)
    print(digest)
    send_summary(service, cfg, digest)


if __name__ == "__main__":
    main()
