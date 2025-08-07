import os
import requests
import json
import time
from dotenv import load_dotenv
from datetime import datetime, timezone
import praw
from urllib.parse import quote
import re
from openai import OpenAI
import subprocess

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")

# OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Config
SUBREDDITS = ["caregivers", "AgingParents", "Connecticut"]
SEEN_FILE = "seen_urls.txt"


def load_seen_urls():
    seen = set()
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            seen = set(line.strip() for line in f)
    return seen


def save_seen_urls(seen_urls):
    with open(SEEN_FILE, "w") as f:
        for url in seen_urls:
            f.write(url + "\n")


def scrape_reddit_posts():
    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT
    )
    seen_urls = load_seen_urls()
    new_leads = []

    for subreddit_name in SUBREDDITS:
        subreddit = reddit.subreddit(subreddit_name)
        for post in subreddit.new(limit=25):
            url = f"https://www.reddit.com{post.permalink}"
            if url in seen_urls:
                continue
            new_leads.append({
                "Full Name or Listing Title": post.title,
                "Post Description / Notes": post.selftext,
                "Date Posted": datetime.fromtimestamp(post.created_utc, tz=timezone.utc).strftime("%Y-%m-%d"),
                "Source URL": url,
                "Location (city/town)": "New Haven County",
                "Phone Number": "N/A",
                "Outreach Status": "Not Contacted",
                "Lead Source": "Reddit"
            })
            seen_urls.add(url)

    save_seen_urls(seen_urls)
    return new_leads


def get_confidence_score(post_text):
    system_prompt = "You score Reddit posts for PCA service lead quality."
    user_prompt = f"""
You are a lead qualification assistant for a home care agency that provides PCA (Personal Care Assistant) and Homemaker Companion services in New Haven County, Connecticut.

Your task is to analyze Reddit posts to determine how likely they represent a **qualified, local lead** for our services.

Score each post from **0 to 100** based on:

1. **Caregiving Need**   Does the post describe a need for caregiving, senior support, in-home assistance, or mention a family member who needs care?
2. **Location Relevance**   Does the post explicitly or implicitly relate to New Haven County or nearby areas in Connecticut?
3. **Lead Intent**   Does the post suggest that the author or someone they know is actively looking for help or open to services?
4. **Actionability**  Is there enough detail that someone could reasonably follow up?

Do **not** score high for vague rants, general info-sharing, or non-local discussions.

Only return a JSON object in this format (no extra text):

```json
{{
  "confidence_score": 0-100,
  "reason": "Explain in 1-2 sentences why this score was given, including location and care relevance."
}}

Post:
{post_text}
"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo-0125",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=150
        )
        raw = response.choices[0].message.content
        try:
            json_text = re.search(r"{.*}", raw, re.DOTALL).group()
            output = json.loads(json_text)
            return output.get("confidence_score", 0), output.get("reason", "")
        except Exception as e:
            print("❌ JSON parse error:", e)
            print("🔎 Raw content:", raw)
            return 0, "LLM response unreadable"
    except Exception as e:
        print("OpenAI error:", e)

    return 0, "LLM scoring failed"


def upload_to_airtable(leads):
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{quote(AIRTABLE_TABLE_NAME)}"

    for lead in leads:
        fields = lead.copy()
        data = {"fields": fields}
        response = requests.post(url, headers=headers, json=data)
        if response.status_code not in [200, 201]:
            print("❌ Failed to upload:", response.text)
        else:
            print(f"✅ Uploaded: {lead.get('Full Name or Listing Title')}")


def run_pipeline():
    leads = scrape_reddit_posts()
    print(f"🔎 Found {len(leads)} new leads")

    scored_leads = []
    for lead in leads:
        score, reason = get_confidence_score(lead["Post Description / Notes"])
        lead["Confidence Score"] = score
        lead["Confidence Reason"] = reason
        scored_leads.append(lead)
        time.sleep(1.2)  # Avoid rate limits

    upload_to_airtable(scored_leads)


def run_all():
    scripts = [
        "airtable_dedup_and_delete_fixed.py",
        "airtable_rescore_leads.py",
        "reddit_lead_pipeline.py",
        "AI_lead_generator.py"
    ]
    for script in scripts:
        print(f"🚀 Running {script}...")
        subprocess.run(["python", script])


def main():
    print("Choose a task:")
    print("1. Run full pipeline")
    print("2. Run only Reddit lead pipeline")
    print("3. Run deduplication script")
    print("4. Run rescoring script")
    print("5. Run AI lead generator")
    choice = input("Enter choice: ").strip()

    if choice == "1":
        run_all()
    elif choice == "2":
        run_pipeline()
    elif choice == "3":
        subprocess.run(["python", "airtable_dedup_and_delete_fixed.py"])
    elif choice == "4":
        subprocess.run(["python", "airtable_rescore_leads.py"])
    elif choice == "5":
        subprocess.run(["python", "AI_lead_generator.py"])
    else:
        print("Invalid choice.")


if __name__ == "__main__":
    main()
