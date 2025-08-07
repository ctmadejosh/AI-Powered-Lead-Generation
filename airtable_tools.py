import os
import time
import json
import argparse
from datetime import datetime, timezone
from urllib.parse import quote
import re


import requests
from dotenv import load_dotenv

try:
    import praw
except ImportError:
    praw = None

load_dotenv()

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME")
AIRTABLE_OUTREACH_LOG_TABLE = os.getenv("AIRTABLE_OUTREACH_LOG_TABLE", "Outreach Log")

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_API_KEY}",
    "Content-Type": "application/json",
}

BASE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"
LEADS_URL = f"{BASE_URL}/{quote(AIRTABLE_TABLE_NAME)}"
LOG_URL = f"{BASE_URL}/{quote(AIRTABLE_OUTREACH_LOG_TABLE)}"

def startup_check():
    print("\n🔧 Environment Configuration:")
    vars_to_check = [
        "AIRTABLE_API_KEY",
        "AIRTABLE_BASE_ID",
        "AIRTABLE_TABLE_NAME",
        "AIRTABLE_OUTREACH_LOG_TABLE",
        "REDDIT_CLIENT_ID",
        "REDDIT_CLIENT_SECRET",
        "REDDIT_USER_AGENT",
        "REDDIT_USERNAME",
        "REDDIT_PASSWORD",
        "OUTREACH_MESSAGE",
        "DELETE_THRESHOLD",
        "OUTREACH_THRESHOLD",
        "OUTREACH_SLEEP"
    ]
    for var in vars_to_check:
        val = os.getenv(var)
        if val:
            display_val = val if "KEY" not in var and "PASSWORD" not in var and "SECRET" not in var else "***HIDDEN***"
            print(f"✅ {var} = {display_val}")
        else:
            print(f"⚠️ {var} is NOT set")
    print("\n")

def _airtable_get(url, params=None):
    r = requests.get(url, headers=HEADERS, params=params or {})
    r.raise_for_status()
    return r.json()

def _airtable_post(url, payload):
    r = requests.post(url, headers=HEADERS, json=payload)
    r.raise_for_status()
    return r.json()

def _airtable_patch(url, payload):
    r = requests.patch(url, headers=HEADERS, json=payload)
    r.raise_for_status()
    return r.json()

def fetch_records(filter_formula=None):
    records = []
    offset = None
    params = {"pageSize": 100}
    if filter_formula:
        params["filterByFormula"] = filter_formula
    while True:
        if offset:
            params["offset"] = offset
        data = _airtable_get(LEADS_URL, params=params)
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return records

def delete_records_batch(record_ids):
    for i in range(0, len(record_ids), 10):
        batch = record_ids[i:i+10]
        r = requests.delete(LEADS_URL, headers=HEADERS, params={"records[]": batch})
        if r.status_code != 200:
            print(f"❌ Failed to delete batch {batch}: {r.status_code} {r.text}")
        else:
            print(f"🗑️ Deleted {len(batch)} records")

def cmd_prune(args):
    formula = f"{{Confidence Score}} < {args.threshold}"
    if args.source:
        formula = f"AND({formula}, {{Lead Source}} = '{args.source}')"
    records = fetch_records(filter_formula=formula)
    if not records:
        print("✅ No records to delete")
        return
    if args.dry_run:
        print(f"💡 Dry run: {len(records)} would be deleted")
        return
    if not args.yes:
        confirm = input(f"Delete {len(records)} records? [y/N]: ").strip().lower()
        if confirm != 'y':
            print("🚫 Aborted")
            return
    ids = [r["id"] for r in records]
    delete_records_batch(ids)
    print("✅ Prune complete")

def get_logged_post_urls():
    logged = set()
    offset = None
    while True:
        params = {"pageSize": 100}
        if offset:
            params["offset"] = offset
        data = _airtable_get(LOG_URL, params=params)
        for rec in data.get("records", []):
            url = rec.get("fields", {}).get("Post URL")
            if url:
                logged.add(url)
        offset = data.get("offset")
        if not offset:
            break
    return logged

def make_reddit_client():
    if praw is None:
        raise RuntimeError("praw not installed")
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent=os.getenv("REDDIT_USER_AGENT"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
    )

def default_reply(fields):
    template = os.getenv("OUTREACH_MESSAGE")
    mapping = {
        "title": fields.get("Full Name or Listing Title", "your post"),
        "username": fields.get("Reddit Username", "there"),
        "score": fields.get("Confidence Score", ""),
        "post_url": fields.get("Source URL", ""),
    }
    if template:
        try:
            return template.format(**mapping)
        except Exception:
            pass
    return (
        "Hi there! 👋 I noticed your post and wanted to offer some help.\n\n"
        "We provide Personal Care Assistant and Homemaker Companion services in New Haven County, CT — including overnight, live-in, and 12-hour shifts (min 4 hours).\n\n"
        "Call or text (203) 444-6194 or our office (203) 298-4867 Mon–Fri 9am–5pm. Happy to answer questions and discuss options."
    )

def update_lead_outreach_status(record_id, status="Contacted"):
    _airtable_patch(f"{LEADS_URL}/{record_id}", {"fields": {"Outreach Status": status}})

def log_outreach(fields, message):
    payload = {
        "fields": {
            "Reddit Username": fields.get("Reddit Username", "Unknown"),
            "Message Sent": message,
            "Post URL": fields.get("Source URL"),
            "Confidence Score": fields.get("Confidence Score"),
            "Timestamp": datetime.now(timezone.utc).isoformat(),
            "Lead Title": fields.get("Full Name or Listing Title"),
        }
    }
    _airtable_post(LOG_URL, payload)

def cmd_outreach(args):
    formula = f"{{Confidence Score}} >= {args.threshold}"
    records = fetch_records(filter_formula=formula)
    if not records:
        print("✅ No candidates for outreach")
        return

    logged_urls = get_logged_post_urls()
    reddit = make_reddit_client()

    sent = 0
    for rec in records:
        fields = rec.get("fields", {})
        url = fields.get("Source URL")
        if not url or url in logged_urls:
            continue

        # Extract Reddit post id from permalink
        try:
            post_id = url.rstrip("/").split("/")[6]
        except Exception:
            print(f"⚠️ Invalid Reddit URL: {url}")
            continue

        # Try to reply with RATELIMIT-aware backoff
        tries = 0
        while True:
            try:
                submission = reddit.submission(id=post_id)
                message = default_reply(fields)
                if args.dry_run:
                    print(f"📝 DRY RUN — would reply to {url} with:\n{message}\n")
                    break

                submission.reply(message)
                print(f"💬 Replied to: {url}")
                log_outreach(fields, message)
                update_lead_outreach_status(rec["id"])
                sent += 1
                time.sleep(args.sleep)  # small fixed delay after a success
                break

            except Exception as e:
                err = str(e)
                # Example: RATELIMIT: "Looks like you've been doing that a lot. Take a break for 7 minutes ..."
                if "RATELIMIT" in err.upper():
                    m = re.search(r"(\d+)\s*(minute|second)", err, re.IGNORECASE)
                    if m:
                        n = int(m.group(1))
                        unit = m.group(2).lower()
                        wait_s = n * 60 if unit.startswith("minute") else n
                    else:
                        wait_s = 60
                    wait_s += 5  # safety buffer
                    tries += 1
                    if tries > 5:
                        print(f"⛔ Rate limited too many times on {url}. Skipping.")
                        break
                    print(f"⏳ Rate limited — waiting {wait_s} seconds (attempt {tries}/5) before retrying...")
                    time.sleep(wait_s)
                    continue
                else:
                    print(f"❌ Failed to reply to {url}: {e}")
                    break

    print(f"✅ Outreach complete. Messages sent: {sent}")


def run_interactive_menu():
    print("Choose a task:")
    print("1. Prune low-confidence leads")
    print("2. Outreach to high-confidence leads")
    choice = input("Enter choice: ").strip()
    if choice == "1":
        threshold = input("Delete leads with Confidence Score BELOW what number? [default 40]: ").strip() or os.getenv("DELETE_THRESHOLD", "40")
        source = input("Limit to Lead Source (press Enter for all): ").strip()
        args = argparse.Namespace(threshold=int(threshold), source=source if source else None, dry_run=False, yes=False, func=cmd_prune)
        args.func(args)
    elif choice == "2":
        threshold = input("Outreach threshold (Confidence Score >= ? ) [default 80]: ").strip() or os.getenv("OUTREACH_THRESHOLD", "80")
        sleep_time = input("Seconds to sleep between replies [default 30]: ").strip() or os.getenv("OUTREACH_SLEEP", "30")
        args = argparse.Namespace(threshold=int(threshold), sleep=int(sleep_time), dry_run=False, func=cmd_outreach)
        args.func(args)
    else:
        print("Invalid choice")

def main():
    startup_check()
    if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME]):
        raise SystemExit("Missing Airtable env vars")
    run_interactive_menu()

if __name__ == "__main__":
    main()
