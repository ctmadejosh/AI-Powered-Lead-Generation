"""
Craigslist Lead Generator
==========================

This script scrapes Craigslist for posts related to PCA (Personal Care Assistant),
Homemaker Companion, or eldercare services in the New Haven County area. It is
designed to complement other lead-generation tools such as the Reddit lead scraper.

The script looks through multiple pages of Craigslist results and filters listings
that contain relevant caregiving keywords. It extracts information such as title,
description, posting date, contact phone number, and location, then uploads the leads
to Airtable for further processing or outreach.

Environment variables required:

  AIRTABLE_BASE_ID       - your Airtable base ID
  AIRTABLE_TABLE_NAME    - name of the Airtable table (e.g. "Leads")
  AIRTABLE_API_KEY       - your Airtable personal access token

Usage:

  python AI_lead_generator.py

This will:

  - Search Craigslist's "lessons & services" section for relevant posts
  - Parse and extract details (including phone numbers)
  - Push matching leads into Airtable under "Craigslist" as the source
  - Automatically tag posts with "Not Contacted" as the outreach status

You can customize the number of pages to scrape by changing the `pages` parameter
inside the `get_listings()` function.

Note: This script does not perform duplicate checking on its own. To avoid duplicate
uploads, use a separate deduplication script or add logic to check Airtable before inserting.
"""

import requests
from bs4 import BeautifulSoup
import re
import os
from dotenv import load_dotenv

load_dotenv()

# Airtable config
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")

AIRTABLE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_API_KEY}",
    "Content-Type": "application/json"
}

# Craigslist search URL
BASE_URL = "https://newhaven.craigslist.org"
SEARCH_URL = f"{BASE_URL}/search/lss?query=caregiver|companion|PCA"

def get_listings(pages=3):  # Set how many pages you want to scrape
    leads = []

    for page in range(pages):
        offset = page * 120
        url = f"{BASE_URL}/search/lss?query=caregiver|companion|PCA&s={offset}"
        print(f"Scraping page {page + 1}: {url}")

        soup = BeautifulSoup(requests.get(url).text, "html.parser")
        posts = soup.select(".result-info")

        for post in posts:
            title = post.find("a", class_="result-title").text.strip()
            link = post.find("a", class_="result-title")["href"]
            date = post.find("time")["datetime"]
            location = post.select_one(".result-hood")
            location = location.text.strip(" ()") if location else "New Haven County"

            # Fetch post details
            post_soup = BeautifulSoup(requests.get(link).text, "html.parser")
            description = post_soup.select_one("#postingbody").text.strip()
            contact_info = re.findall(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", description)
            phone = contact_info[0] if contact_info else "N/A"

            if any(keyword in description.lower() for keyword in ["care", "pca", "companion", "elder"]):
                leads.append({
                    "title": title,
                    "description": description,
                    "location": location,
                    "phone": phone,
                    "date": date,
                    "url": link
                })

    return leads

def upload_to_airtable(leads):
    for lead in leads:
        data = {
            "fields": {
                "Full Name or Listing Title": lead["title"],
                "Post Description / Notes": lead["description"],
                "Phone Number": lead["phone"],
                "Location (city/town)": lead["location"],
                "Date Posted": lead["date"].split("T")[0],
                "Lead Source": "Craigslist",  # Make sure 'Craigslist' exists as an option in Airtable
                "Source URL": lead["url"],
                "Outreach Status": "Not Contacted"
            }
        }
        res = requests.post(AIRTABLE_URL, json=data, headers=HEADERS)
        if res.status_code != 200:
            print("Error uploading:", res.text)

if __name__ == "__main__":
    leads = get_listings()
    print(f"Found {len(leads)} leads.")
    upload_to_airtable(leads)
