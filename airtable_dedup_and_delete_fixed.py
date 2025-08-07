"""Airtable De-duplication Script
==============================

This script is used to clean up the Airtable base by identifying and deleting duplicate records.
It looks for duplicate entries based on the "Source URL" field, which acts as a unique identifier
for leads.

It's recommended to run this after scraping or batch uploading to ensure your table stays clean
and avoids redundancy.

Environment variables required:

  AIRTABLE_BASE_ID    - the ID of your Airtable base
  AIRTABLE_TABLE_NAME - the name of the table to modify (e.g. "Leads")
  AIRTABLE_API_KEY    - your Airtable personal access token

Usage:

  python airtable_dedup_and_delete_fixed.py

This will fetch all records in the table, find entries with the same "Source URL", and delete
the oldest duplicates while keeping the most recent one. It prints out the records it deletes.

"""


import os
import requests
from dotenv import load_dotenv
from collections import defaultdict

# Load Airtable credentials
load_dotenv()
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")

SEEN_FILE = "seen_urls.txt"

def load_seen_urls():
    seen = set()
    try:
        with open(SEEN_FILE, "r") as f:
            seen = set(line.strip() for line in f)
    except FileNotFoundError:
        pass
    return seen

def save_seen_urls(seen_urls):
    with open(SEEN_FILE, "w") as f:
        for url in seen_urls:
            f.write(url + "\n")

def fetch_airtable_records():
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}"
    }
    records = []
    offset = None
    while True:
        params = {"pageSize": 100}
        if offset:
            params["offset"] = offset
        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            raise Exception(f"Airtable API error: {response.text}")
        data = response.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return records

def delete_duplicate_records(duplicate_record_ids):
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
    for i in range(0, len(duplicate_record_ids), 10):
        batch = duplicate_record_ids[i:i+10]
        params = {"records[]": batch}
        response = requests.delete(url, headers=headers, params=params)
        if response.status_code != 200:
            print(f"❌ Failed to delete batch: {batch} — {response.text}")
        else:
            print(f"🗑 Deleted {len(batch)} duplicate records")

def deduplicate_airtable():
    seen_urls = load_seen_urls()
    records = fetch_airtable_records()
    new_urls = set()
    duplicates_to_delete = []

    url_to_record_ids = defaultdict(list)
    for record in records:
        fields = record.get("fields", {})
        url = fields.get("Source URL")
        if url:
            url_to_record_ids[url].append(record["id"])

    for url, record_ids in url_to_record_ids.items():
        if len(record_ids) > 1:
            duplicates_to_delete.extend(record_ids[1:])
        if url not in seen_urls:
            new_urls.add(url)

    if duplicates_to_delete:
        delete_duplicate_records(duplicates_to_delete)

    save_seen_urls(seen_urls.union(new_urls))
    print(f"✅ Deduplicated: {len(duplicates_to_delete)} duplicates deleted from Airtable")

if __name__ == "__main__":
    deduplicate_airtable()
