
# reddit_outreach_log.py
import os, sys, subprocess, time, json, re
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

def sanity_check():
    print("🐍 Python:", sys.executable)
    try:
        import requests as _rq
        print(f"✅ requests v{_rq.__version__} @ {_rq.__file__}")
    except Exception as e:
        print("❌ requests import failed. Activate your venv and run: pip install -r requirements.txt")
        raise
    # quick prompt check so braces in f-strings don't explode later
    try:
        _ = "Okay {{}}, we're good."
        print("✅ Prompt formatting safe (brace test passed)")
    except Exception as e:
        print("❌ Prompt formatting issue:", e)

def _run_script(script, *args, check=True):
    py = sys.executable
    cmd = [py, script, *args]
    print("\n🚀 Running:", " ".join(cmd))
    return subprocess.run(cmd, check=check)

def run_all():
    # Full pipeline in sequence
    sequence = [
    ("airtable_dedup_and_delete_fixed.py", []),                                   # de-dupe
    ("airtable_rescore_leads.py", []),                                            # rescore
    ("airtable_tools.py", [
        "prune",
        "--threshold", os.getenv("DELETE_THRESHOLD", "40"),
        # Optionally limit source, e.g. uncomment next two for Reddit-only:
        # "--source", "Reddit",
    ]),
    ("reddit_lead_pipeline.py", []),                                              # scrape + score (Reddit)
    ("AI_lead_generator.py", []),                                                 # scrape (Craigslist)
    # --- NEW: prune low-confidence ---
    ("airtable_tools.py", [
        "prune",
        "--threshold", os.getenv("DELETE_THRESHOLD", "40"),
        # Optionally limit source, e.g. uncomment next two for Reddit-only:
        # "--source", "Reddit",
    ]),
    # --- NEW: outreach to high-confidence + log ---
    ("airtable_tools.py", [
        "outreach",
        "--threshold", os.getenv("OUTREACH_THRESHOLD", "80"),
        "--sleep", os.getenv("OUTREACH_SLEEP", "30"),
        # add "--dry-run" here if you want to test without posting
    ]),
]
    for script, args in sequence:
        try:
            _run_script(script, *args, check=True)
        except subprocess.CalledProcessError as e:
            print(f"⚠️ {script} failed (exit {e.returncode}). Continuing...")

def menu():
    print("\n=== Lead Gen Control Center ===")
    print("1. Run full pipeline")
    print("2. Run only Reddit lead pipeline")
    print("3. Run deduplication (Airtable)")
    print("4. Run rescoring (Airtable + LLM)")
    print("5. Run Craigslist scraper")
    print("6. Prune low-confidence leads (delete)")
    print("7. Outreach to high-confidence leads and log")
    print("0. Exit")
    return input("Select: ").strip()

def main():
    sanity_check()
    while True:
        choice = menu()
        if choice == "1":
            run_all()
        elif choice == "2":
            _run_script("reddit_lead_pipeline.py")
        elif choice == "3":
            _run_script("airtable_dedup_and_delete_fixed.py")
        elif choice == "4":
            _run_script("airtable_rescore_leads.py")
        elif choice == "5":
            _run_script("AI_lead_generator.py")
        elif choice == "6":
            th = input("Delete leads with Confidence Score BELOW [default 40]: ").strip() or "40"
            src = input("Limit to Lead Source (press Enter for all): ").strip()
            args = ["prune", "--threshold", th]
            if src:
                args += ["--source", src]
            _run_script("airtable_tools.py", *args, check=False)
        elif choice == "7":
            th = input("Outreach threshold (Confidence Score >= ?) [default 80]: ").strip() or "80"
            sl = input("Seconds to sleep between replies [default 30]: ").strip() or "30"
            _run_script("airtable_tools.py", "outreach", "--threshold", th, "--sleep", sl, check=False)
        elif choice == "0":
            print("Bye 👋")
            break
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()
