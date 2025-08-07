# 🧠 AI-Powered Lead Generation & Outreach Automation

## Overview
This project is an **end-to-end automated lead generation and outreach system** built for a home care agency in **New Haven County, Connecticut**.  
It leverages **Python**, **OpenAI**, **Reddit API**, and **Airtable** to find, score, and engage potential clients efficiently.

The automation:
- Scrapes Reddit caregiving-related posts for potential leads
- Scores leads with AI based on caregiving need, location relevance, and intent
- Uploads leads into Airtable with detailed scoring rationale
- Automatically replies to high-confidence leads
- Logs all outreach activity in a dedicated Airtable table

---

## Features
- **Reddit Scraper** – Finds relevant posts across specified subreddits  
- **AI Confidence Scoring** – Uses GPT to assign scores from 0–100  
- **Airtable Integration** – Stores leads and outreach logs  
- **Automated Outreach** – Sends pre-written responses to qualified leads  
- **Duplicate Detection** – Prevents reprocessing the same posts

---

## Tech Stack
- **Python 3.12+**
- [PRAW](https://praw.readthedocs.io/) – Reddit API wrapper
- [Requests](https://docs.python-requests.org/) – HTTP requests
- [OpenAI Python SDK](https://github.com/openai/openai-python) – AI confidence scoring
- [Airtable API](https://airtable.com/api) – Lead storage & logging
- [python-dotenv](https://github.com/theskumar/python-dotenv) – Environment variable management

---

## Installation

1. **Clone the repo**
```bash
git clone https://github.com/yourusername/homecare-lead-generator.git
cd homecare-lead-generator
```

## Create Virtual Env
```bash
python -m venv venv
source venv/bin/activate   # Mac/Linux
venv\Scripts\activate      # Windows
```
## Install Dependencies
```bash
pip install -r requirements.txt
```
## Set env Variables in a .env separately
```bash 
OPENAI_API_KEY=your_openai_key

AIRTABLE_API_KEY=your_airtable_key

AIRTABLE_BASE_ID=your_base_id

AIRTABLE_TABLE_NAME=Leads

AIRTABLE_OUTREACH_LOG_TABLE=Outreach Log

REDDIT_CLIENT_ID=your_reddit_client_id

REDDIT_CLIENT_SECRET=your_reddit_client_secret

REDDIT_USER_AGENT=your_user_agent
```
