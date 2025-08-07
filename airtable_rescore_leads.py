"""
Airtable Confidence Rescorer
============================

This script re-scores all Reddit-based leads in your Airtable using an LLM (OpenAI GPT-3.5)
based on the content of the "Post Description / Notes" field. This is useful for retroactive
updates if your scoring prompt or model changes over time.

Environment variables required:

  AIRTABLE_BASE_ID    - the ID of your Airtable base
  AIRTABLE_TABLE_NAME - the name of the table to update (e.g. "Leads")
  AIRTABLE_API_KEY    - your Airtable personal access token
  OPENAI_API_KEY      - your OpenAI key for calling ChatCompletion

Usage:

  python airtable_rescore_leads.py

The script fetches all records in the table, analyzes the post text, and updates each
record's "Confidence Score" and "Confidence Reason" fields directly in Airtable.

"""


import os
import requests
import json
from dotenv import load_dotenv
from urllib.parse import quote
from datetime import datetime
import openai
import re

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME")

openai.api_key = OPENAI_API_KEY

# Fetch records from Airtable
def fetch_airtable_records():
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}"
    }
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{quote(AIRTABLE_TABLE_NAME)}"

    records = []
    offset = None

    while True:
        params = {"pageSize": 100}
        if offset:
            params["offset"] = offset

        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            print("❌ Failed to fetch records:", response.text)
            break

        data = response.json()
        records.extend(data.get("records", []))

        offset = data.get("offset")
        if not offset:
            break

    return records

# Get confidence score from OpenAI
def get_confidence_score(post_text):
    system_prompt = "You score Reddit posts for PCA service lead quality."
    user_prompt = f"""
You are a lead qualification assistant for a home care agency that provides PCA (Personal Care Assistant) and Homemaker Companion services in New Haven County, Connecticut.

Your task is to analyze Reddit posts to determine how likely they represent a **qualified, local lead** for our services.

Score each post from **0 to 100** based on:

1. **Caregiving Need**
2. **Location Relevance**
3. **Lead Intent**
4. **Actionability**

Only return a JSON object like this:

{{
  "confidence_score": 0-100,
  "reason": "Brief explanation"
}}

Post:
{post_text}
"""

    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo-0125",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=150
        )
        raw = response.choices[0].message.content
        json_text = re.search(r"{.*}", raw, re.DOTALL).group()
        data = json.loads(json_text)
        return int(data.get("confidence_score", 0)), data.get("reason", "")
    except Exception as e:
        print("OpenAI error:", e)
        return 0, "LLM error"

# Update Airtable with new score and reason
def update_airtable_record(record_id, score, reason):
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{quote(AIRTABLE_TABLE_NAME)}/{record_id}"

    payload = {
        "fields": {
            "Confidence Score": score,
            "Confidence Reason": reason
        }
    }

    response = requests.patch(url, headers=headers, json=payload)
    if response.status_code not in [200, 201]:
        print(f"❌ Failed to update record {record_id}:", response.text)
    else:
        print(f"✅ Updated record {record_id} with score {score}")

# Main function to rescore all records
def rescore_all():
    records = fetch_airtable_records()
    for record in records:
        fields = record.get("fields", {})
        post_text = fields.get("Post Description / Notes")
        if not post_text:
            continue

        score, reason = get_confidence_score(post_text)
        update_airtable_record(record["id"], score, reason)

if __name__ == "__main__":
    rescore_all()
