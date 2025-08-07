"""
Reddit Lead Generator
=====================

This script is designed to complement the existing Craigslist lead generator by
pulling potential clients from Reddit. It uses Reddit's public JSON endpoints
to search a handful of relevant subreddits for posts that mention caregiver
needs, PCA services, companions or similar in the New Haven, Connecticut area.
The results are pushed into the same Airtable base used by the Craigslist
scraper. You can customise the list of subreddits and keywords at the top of
the script.

Environment variables required:

  AIRTABLE_BASE_ID    - the ID of your Airtable base
  AIRTABLE_TABLE_NAME - the name of the table to populate (e.g. "Leads")
  AIRTABLE_API_KEY    - your Airtable personal access token

Usage:

  python reddit_lead_generator.py

This will fetch posts from each subreddit specified, filter them for
keywords, extract simple contact information (phone numbers if present),
then upload them to Airtable. Each run is idempotent with respect to
Airtable since the Reddit URL acts as a unique identifier; Airtable will
append duplicates if you run the script multiple times without additional
de-duplication logic.

"""

import os
import re
import time
from datetime import datetime, timezone
from typing import Dict, List

# Load previously seen post URLs to prevent duplicates
SEEN_POSTS_FILE = "seen_posts.txt"
seen_urls = set()
if os.path.exists(SEEN_POSTS_FILE):
    with open(SEEN_POSTS_FILE, "r") as f:
        seen_urls = set(line.strip() for line in f)


import requests
from dotenv import load_dotenv

load_dotenv()

# Airtable configuration
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")

if not all([AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME, AIRTABLE_API_KEY]):
    raise RuntimeError(
        "Missing Airtable configuration. Please set AIRTABLE_BASE_ID, "
        "AIRTABLE_TABLE_NAME and AIRTABLE_API_KEY in your environment or .env file."
    )

# Airtable API endpoint and headers
AIRTABLE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_API_KEY}",
    "Content-Type": "application/json",
}

# Subreddits to search for potential leads. Feel free to add more
SUBREDDITS: List[str] = [
    "Connecticut",
    "NewHaven",
    "caregivers",
    "HomeHealth",
    "agingparents",
]

# Keywords to look for in posts. All comparisons are case‑insensitive
KEYWORDS: List[str] = [
    "caregiver",
    "pca",
    "companion",
    "home care",
    "homemaker",
]

# Maximum number of posts to fetch per subreddit. Reddit's unauthenticated
# JSON API returns 25 items by default; using limit=100 yields up to 100 items.
POST_LIMIT = 50

def fetch_reddit_posts(subreddit: str) -> List[Dict[str, str]]:
    """Fetch posts from a given subreddit using Reddit's JSON search endpoint.

    Parameters
    ----------
    subreddit: str
        The subreddit name without the /r/ prefix.

    Returns
    -------
    List[Dict[str, str]]
        A list of post dictionaries with basic information.
    """
    query = " OR ".join(KEYWORDS)
    url = (
        f"https://www.reddit.com/r/{subreddit}/search.json"
        f"?q={requests.utils.quote(query)}"
        "&restrict_sr=1&sort=new&limit=" + str(POST_LIMIT)
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (ChatGPTLeadScraper/1.0)",
    }
    print(f"Fetching posts from r/{subreddit} ...")
    try:
        response = requests.get(url, headers=headers, timeout=15)
    except requests.RequestException as exc:
        print(f"Error fetching posts from r/{subreddit}: {exc}")
        return []
    if response.status_code != 200:
        print(f"Non‑200 response from Reddit for r/{subreddit}: {response.status_code}")
        return []
    try:
        data = response.json()
    except ValueError:
        print(f"Could not decode JSON from r/{subreddit}")
        return []
    # Extract posts from the JSON structure
    posts = data.get("data", {}).get("children", [])
    return [post.get("data", {}) for post in posts]


def parse_posts(posts: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Parse raw Reddit posts and filter out those that do not match keywords.

    Parameters
    ----------
    posts: List[Dict[str, str]]
        Raw posts from the Reddit API.

    Returns
    -------
    List[Dict[str, str]]
        Filtered list of leads with relevant fields extracted.
    """
    leads = []
    for post in posts:
        title = post.get("title", "").strip()
        # Combine selftext and title for keyword search
        description = post.get("selftext", "").strip()
        text_for_search = f"{title} {description}".lower()
        if not any(keyword.lower() in text_for_search for keyword in KEYWORDS):
            continue
        # Some posts might indicate location in flair or title; if not, default to New Haven County
        location = "New Haven County"
        # Attempt to extract a phone number from the text
        phone_match = re.findall(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", description + " " + title)
        phone = phone_match[0] if phone_match else "N/A"
        # Date the post was created, convert from epoch to ISO 8601
        created_utc = post.get("created_utc")
        if created_utc:
            date = datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat()
        else:
            date = ""
        # Build the Reddit URL
        permalink = post.get("permalink", "")
        url = f"https://www.reddit.com{permalink}" if permalink else ""
        # Compose the lead dictionary
        if url in seen_urls:
            continue
        leads.append({
            "title": title,
            "description": description or title,
            "location": location,
            "phone": phone,
            "date": date,
            "url": url,
        })
    return leads


def upload_to_airtable(leads: List[Dict[str, str]], source: str = "Reddit") -> None:
    """Upload a list of leads to Airtable.

    Parameters
    ----------
    leads: List[Dict[str, str]]
        A list of leads with keys matching the Airtable fields.
    source: str
        The lead source label to record in Airtable.
    """
    if not leads:
        print("No leads to upload.")
        return
    for lead in leads:
        # Construct the payload according to your Airtable schema
        payload = {
            "fields": {
                # Use the field names exactly as they appear in your Airtable table.  
                # The default "Full Name or Listing Title" and "Post Description / Notes"
                # correspond to the template schema shared with this project.  
                "Full Name or Listing Title": lead["title"],
                "Post Description / Notes": lead["description"],
                "Phone Number": lead["phone"],
                "Location (city/town)": lead["location"],
                "Date Posted": lead["date"].split("T")[0],  # Keeps only the 'YYYY-MM-DD' part
                "Lead Source": source,
                "Source URL": lead["url"],
                "Outreach Status": "Not Contacted",
            }
        }
        try:
            res = requests.post(AIRTABLE_URL, json=payload, headers=HEADERS, timeout=15)
        except requests.RequestException as exc:
            print(f"Error uploading lead to Airtable: {exc}")
            continue
        if res.status_code != 200:
            print(f"Airtable returned status {res.status_code}: {res.text}")


def run_scraper() -> None:
    """Fetch, parse and upload leads from multiple subreddits."""
    all_leads: List[Dict[str, str]] = []
    for subreddit in SUBREDDITS:
        posts = fetch_reddit_posts(subreddit)
        parsed = parse_posts(posts)
        print(f"Found {len(parsed)} relevant posts in r/{subreddit}.")
        all_leads.extend(parsed)
        # respectful delay between subrequests to avoid hitting rate limits
        time.sleep(2)
    # Upload to Airtable if there are any leads
    upload_to_airtable(all_leads, source="Reddit")

    # Save new post URLs after upload
    with open(SEEN_POSTS_FILE, "a") as f:
        for lead in all_leads:
            f.write(lead["url"] + "\n")

    print(f"Uploaded {len(all_leads)} leads to Airtable.")


if __name__ == "__main__":
    run_scraper()