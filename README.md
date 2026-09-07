# Gmail Morning Summary

Every morning at **8:00 AM**, a script reads your last 24 hours of Gmail,
filters out the noise (promotions, social, newsletters, account
notifications), summarizes what remains (sender + subject + 1–2 lines),
and emails you a digest. LinkedIn job offers get their own section.

## Setup

### 1. Install dependencies (uv)

```bash
uv sync
```

### 2. Create Google Cloud credentials (one time, ~5 min)

1. Go to <https://console.cloud.google.com/> and create a project
   (e.g. `gmail-morning-summary`).
2. Enable the **Gmail API**: *APIs & Services → Library → search "Gmail API" → Enable*.
3. Configure the OAuth consent screen: *APIs & Services → OAuth consent screen*.
   - User type: **External**, fill in the app name and your email.
   - On the **Scopes** step add:
     - `.../auth/gmail.readonly`
     - `.../auth/gmail.send`
   - On the **Test users** step, add your own Gmail address.
   - **Important:** after saving, click **"Publish app"** (move it to
     *In production*). Otherwise your refresh token expires every 7 days
     and you'll have to re-authorize weekly. Google will show an
     "unverified app" warning during authorization — it's your own app,
     click *Advanced → Go to … (unsafe)* to proceed.
4. Create credentials: *APIs & Services → Credentials → Create Credentials
   → OAuth client ID → Application type: Desktop app*.
5. Download the JSON, rename it to `credentials.json`, and put it in this
   folder (next to `gmail_summarizer.py`).

### 3. First run (one-time browser authorization)

```bash
uv run gmail_summarizer.py
```

A browser window opens — sign in with your Google account and approve.
This creates `token.json`; after that the script runs unattended.
You'll also immediately receive a test summary email.

### 4. Schedule it for 8:00 AM

```bash
./setup_launchd.sh
```

This installs a `launchd` agent that runs the script daily at 08:00
(your Mac needs to be on/awake at that time).

## Configuration

Edit `config.json`:

| Key | Meaning |
|---|---|
| `send_to` | `"me"` = same account, or an email address |
| `lookback_hours` | How far back to look (default 24) |
| `exclude_categories` | Gmail categories to skip (`promotions`, `social`, `forums`, `updates`) |
| `exclude_newsletters` | Skip anything with a `List-Unsubscribe` header |
| `account_notification_keywords` | Subjects/snippets containing these are skipped |
| `linkedin.enabled` | Toggle the LinkedIn job offers section |
| `linkedin.job_offer_keywords` | What counts as a job offer email |
| `summary_max_chars` | Max length of each 1–2 line summary |
| `max_emails` | Safety cap on emails processed per run |

## Notes

- The LinkedIn "interesting to me" logic is a placeholder in
  `is_interesting_job_offer()` (currently includes all job alerts) —
  to be refined.
- Summaries are extractive (taken from the email text). An LLM-based
  summarizer can be added later.
- Secrets (`credentials.json`, `token.json`) are git-ignored.
- Logs from scheduled runs: `launchd.out.log`, `launchd.err.log`.
