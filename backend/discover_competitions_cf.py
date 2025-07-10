"""
Cloud Function to discover Hockey Victoria competitions and grades.
"""
import json
import re
import time
from datetime import datetime
from urllib.parse import urljoin

import firebase_admin
import requests
from bs4 import BeautifulSoup
from firebase_functions import https_fn
from firebase_admin import initialize_app, firestore
from google.cloud.firestore_v1.document import DocumentReference

# --- Global Variables & Constants ---
# Initialize Firebase Admin SDK safely
try:
    firebase_admin.get_app()
except ValueError:
    initialize_app()

# Constants from the original script
BASE_URL = "https://www.hockeyvictoria.org.au"
COMPETITIONS_URL = urljoin(BASE_URL, "/games/")
COMP_FIXTURE_REGEX = re.compile(r"/games/(\d+)/(\d+)")
CURRENT_YEAR = datetime.now().year

# --- CORS Headers ---
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",  # Adjust for production
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

# --- Logging Setup (Simplified for Cloud Functions) ---
# Cloud Functions integrate with Google Cloud Logging.
# Use print() for info, and for errors, exceptions will be logged.
# For more structured logging, use the standard `logging` module.
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO) # Default level

# --- Utility Functions (Adapted or Inlined from backend.utils) ---
def make_request(url, session=None, retries=3, delay=5, timeout=15):
    """
    Makes an HTTP GET request.
    Uses provided session or creates a new one.
    """
    requester = session if session else requests.Session()
    try:
        response = requester.get(url, timeout=timeout)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4XX or 5XX)
        return response
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for {url}: {e}")
        return None

def clean_text(text):
    """Basic text cleaning."""
    if text is None:
        return ""
    return text.strip().replace('\n', ' ').replace('\r', '')

# --- Core Logic Functions (from discover_competitions.py) ---

def sanitize_for_firestore(data):
    """Clean and validate data for Firestore compatibility."""
    if not isinstance(data, dict):
        return data
    clean_data = {}
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, dict):
            clean_data[key] = sanitize_for_firestore(value)
        elif isinstance(value, list):
            clean_data[key] = [sanitize_for_firestore(item) if isinstance(item, dict) else item for item in value]
        elif isinstance(value, (str, int, float, bool, datetime, DocumentReference)):
            clean_data[key] = value
        else:
            try:
                logger.warning(f"Converting {key} of type {type(value)} to string for Firestore.")
                clean_data[key] = str(value)
            except Exception as e:
                logger.warning(f"Skipped field {key} with unconvertible type {type(value)} due to: {e}")
    return clean_data

def discover_competition_links(session=None):
    """Scrape the main competitions page to find all competitions and grades."""
    logger.info(f"Discovering competitions from: {COMPETITIONS_URL}")
    response = make_request(COMPETITIONS_URL, session=session)
    if not response:
        logger.error(f"Failed to get competitions page: {COMPETITIONS_URL}")
        return {}, []

    soup = BeautifulSoup(response.text, "html.parser")
    competitions = {}
    grades = []
    current_comp_id = None
    current_comp_name = None

    for element in soup.select("div.p-4, div.px-4.py-2.border-top"):
        heading = element.select_one("h2.h4")
        if heading:
            current_comp_name = clean_text(heading.text)
            download_link = element.select_one("a[href*='/reports/games/']")
            if download_link:
                href = download_link.get("href", "")
                comp_id_match = re.search(r'/reports/games/(\d+)', href)
                if comp_id_match:
                    current_comp_id = comp_id_match.group(1)
                    competitions[current_comp_id] = {
                        "id": current_comp_id, "name": current_comp_name,
                        "url": urljoin(BASE_URL, href), "active": True,
                        "created_at": datetime.now(), "updated_at": datetime.now(),
                    }
            continue

        links = element.select("a")
        for link in links:
            href = link.get("href", "")
            match = COMP_FIXTURE_REGEX.search(href)
            if match:
                comp_id, fixture_id = match.groups()
                grade_name = clean_text(link.text)
                grades.append({
                    "id": fixture_id, "fixture_id": int(fixture_id),
                    "comp_id": int(comp_id), "name": grade_name,
                    "url": urljoin(BASE_URL, href), "active": True,
                    "created_at": datetime.now(), "updated_at": datetime.now(),
                    "last_checked": datetime.now(),
                    "parent_comp_id": current_comp_id,
                    "parent_comp_name": current_comp_name
                })
    logger.info(f"Found {len(competitions)} competitions and {len(grades)} grades.")
    return competitions, grades

def extract_season_year(name, soup_obj):
    """Extract season year from name or page content."""
    year_match = re.search(r'(20\d{2})', name)
    if year_match:
        return int(year_match.group(1))
    if soup_obj:
        for element in soup_obj.select("h1, h2, h3, h4"):
            year_match = re.search(r'(20\d{2})', element.text)
            if year_match:
                return int(year_match.group(1))
    return CURRENT_YEAR

def determine_competition_type(category, name):
    """Determine competition type."""
    name_lower = name.lower()
    # Simplified logic from script
    if "junior" in name_lower or "under" in name_lower or "u1" in name_lower: return "Junior"
    if "senior" in name_lower or "premier" in name_lower or "pennant" in name_lower or "metro" in name_lower: return "Senior"
    if "master" in name_lower or "veteran" in name_lower: return "Masters"
    if "midweek" in name_lower: return "Midweek"
    if "indoor" in name_lower: return "Indoor"
    if "outdoor" in name_lower: return "Outdoor"
    return "Other"

def determine_gender(name):
    """Determine gender from name."""
    name_lower = name.lower()
    if any(term in name_lower for term in ["men", "male", "boys", "men's"]): return "Men"
    if any(term in name_lower for term in ["women", "female", "girls", "women's"]): return "Women"
    if "mixed" in name_lower: return "Mixed"
    return "Unknown"

def get_competition_details(competition, session=None):
    """Fetch additional details for a competition."""
    competition["season"] = str(extract_season_year(competition["name"], None))
    competition["type"] = determine_competition_type(None, competition["name"])
    competition["start_date"] = competition.get("created_at", datetime.now())
    return competition

def get_grade_details(grade, session=None):
    """Fetch additional details for a grade."""
    grade_url = grade["url"]
    logger.info(f"Getting details for grade: {grade['name']} from {grade_url}")
    response = make_request(grade_url, session=session)
    if not response:
        logger.warning(f"Failed to get details for grade: {grade['name']}")
        return grade
    soup = BeautifulSoup(response.text, "html.parser")
    grade["season"] = str(extract_season_year(grade["name"], soup))
    grade["type"] = determine_competition_type("", grade["name"])
    grade["gender"] = determine_gender(grade["name"])
    return grade

def create_or_update_competition(db, comp_data, dry_run=False):
    """Create or update a competition in Firestore."""
    if dry_run:
        logger.info(f"[DRY RUN] Would save competition: {comp_data.get('name', 'unknown')}")
        return True
    try:
        comp_id = comp_data["id"]
        clean_data = sanitize_for_firestore(comp_data)
        comp_ref = db.collection("competitions").document(comp_id)
        comp_ref.set(clean_data, merge=True)
        logger.debug(f"Saved competition {comp_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to save competition {comp_data.get('id', 'unknown')}: {str(e)}")
        return False

def create_or_update_grade(db, grade_data, dry_run=False):
    """Create or update a grade in Firestore."""
    if dry_run:
        logger.info(f"[DRY RUN] Would save grade: {grade_data.get('name', 'unknown')}")
        return True
    try:
        fixture_id_str = str(grade_data["id"])
        parent_comp_id_str = str(grade_data.get("comp_id"))
        if parent_comp_id_str:
            comp_ref_obj = db.collection("competitions").document(parent_comp_id_str)
            grade_data["competition_ref"] = comp_ref_obj
            grade_data["parent_comp_ref"] = comp_ref_obj # Assuming this is intended
        
        clean_data = sanitize_for_firestore(grade_data)
        grade_ref = db.collection("grades").document(fixture_id_str)
        grade_ref.set(clean_data, merge=True)
        logger.debug(f"Saved grade {fixture_id_str}")
        return True
    except Exception as e:
        logger.error(f"Failed to save grade {grade_data.get('id', 'unknown')}: {str(e)}")
        return False

# --- Cloud Function Entry Point ---
@https_fn.on_request()
def discover_competitions_cf(req: https_fn.Request) -> https_fn.Response:
    """
    HTTP-triggered Cloud Function to discover competitions and grades.
    """
    # Handle CORS Preflight Requests
    if req.method == 'OPTIONS':
        return https_fn.Response("", status=204, headers=CORS_HEADERS)

    # Set up logger level based on query param or default
    log_level_param = req.args.get("log_level", "INFO").upper()
    if log_level_param == "DEBUG":
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    logger.info("discover_competitions_cf function triggered.")

    try:
        db = firestore.client()
        
        # Get parameters from request
        # Use CURRENT_YEAR from script as default if not provided
        season_to_process_str = req.args.get("season", str(CURRENT_YEAR))
        try:
            # Ensure season is a string for filtering, as names contain years as strings
            season_to_process = str(int(season_to_process_str))
        except ValueError:
            logger.warning(f"Invalid season format '{season_to_process_str}'. Using current year: {CURRENT_YEAR}")
            season_to_process = str(CURRENT_YEAR)

        is_dry_run = req.args.get("dry_run", "false").lower() == "true"

        logger.info(f"Starting competition discovery for season {season_to_process}. Dry run: {is_dry_run}")
        start_time_total = time.time()

        session = requests.Session()

        competitions, grades = discover_competition_links(session)

        if not competitions:
            logger.error("No competitions found during discovery.")
            return https_fn.Response(
                json.dumps({"status": "error", "message": "No competitions found"}),
                status=500, mimetype="application/json", headers=CORS_HEADERS
            )

        # Filter by season (adapted from script)
        if season_to_process: # Ensure season_to_process is not empty
            logger.info(f"Filtering for season {season_to_process}")
            filtered_competitions = {
                comp_id: comp for comp_id, comp in competitions.items() if season_to_process in comp.get("name", "")
            }
            filtered_grades = [
                grade for grade in grades if season_to_process in grade.get("name", "") or \
                grade.get("parent_comp_id") in filtered_competitions
            ]
            logger.info(f"Found {len(filtered_competitions)} competitions and {len(filtered_grades)} grades for season {season_to_process}")
            competitions = filtered_competitions
            grades = filtered_grades
        
        comp_success_count = 0
        for comp_id, comp_data in competitions.items():
            logger.info(f"Processing competition {comp_id}: {comp_data['name']}")
            comp_data = get_competition_details(comp_data, session)
            if create_or_update_competition(db, comp_data, is_dry_run):
                comp_success_count += 1
        
        grade_success_count = 0
        for i, grade_data in enumerate(grades):
            logger.info(f"Processing grade {i+1}/{len(grades)}: {grade_data['name']} (ID: {grade_data['id']})")
            grade_data = get_grade_details(grade_data, session)
            if create_or_update_grade(db, grade_data, is_dry_run):
                grade_success_count += 1
            time.sleep(0.1) # Reduced delay for CF environment

        duration_total = time.time() - start_time_total
        summary_msg = (
            f"Discovery completed in {duration_total:.2f} seconds. "
            f"Processed {len(competitions)} competitions ({comp_success_count} successful) and "
            f"{len(grades)} grades ({grade_success_count} successful)."
        )
        logger.info(summary_msg)
        if is_dry_run:
            logger.info("DRY RUN - No database changes were made.")

        return https_fn.Response(
            json.dumps({
                "status": "success", 
                "message": summary_msg,
                "data": {
                    "competitions_found": len(competitions),
                    "competitions_saved": comp_success_count,
                    "grades_found": len(grades),
                    "grades_saved": grade_success_count,
                    "duration_seconds": round(duration_total, 2),
                    "season_processed": season_to_process,
                    "dry_run": is_dry_run
                }
            }),
            status=200, mimetype="application/json", headers=CORS_HEADERS
        )

    except Exception as e:
        logger.error(f"Error in discover_competitions_cf: {str(e)}", exc_info=True)
        return https_fn.Response(
            json.dumps({"status": "error", "message": str(e)}),
            status=500, mimetype="application/json", headers=CORS_HEADERS
        )

# It's good practice to ensure this function is available for import in main.py
# (No specific export line needed here, but main.py should import it)
