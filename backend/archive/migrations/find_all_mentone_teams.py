# find_all_mentone_teams.py
#
# Purpose: Simple script to find ALL Mentone teams in existing grades
# No checking or optimization - just scan everything

import firebase_admin
from firebase_admin import credentials, firestore
import requests
from bs4 import BeautifulSoup
import logging
import time
import os
import re

# --- Basic Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"find_all_mentone_teams_{time.strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Constants ---
HV_BASE = "https://www.hockeyvictoria.org.au"
REQUEST_TIMEOUT = 15
MAX_RETRIES = 3
RETRY_DELAY = 1
TEAM_FILTER_KEYWORD = "Mentone"

# --- Regex Patterns ---
TEAM_ID_REGEX = re.compile(r"/games/team/(\d+)/(\d+)")

# --- Helper Functions ---
def make_request(url, retry_count=0):
    """Make an HTTP request with retries."""
    try:
        logger.debug(f"Requesting: {url}")
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'text/html,application/xhtml+xml'
            }
        )
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        if retry_count < MAX_RETRIES:
            wait_time = RETRY_DELAY * (2 ** retry_count)
            logger.warning(f"Request to {url} failed: {e}. Retrying in {wait_time}s...")
            time.sleep(wait_time)
            return make_request(url, retry_count + 1)
        else:
            logger.error(f"Request to {url} failed after {MAX_RETRIES} attempts: {e}")
            return None

def extract_club_info(team_name_text):
    """Extract club name and ID."""
    club_name = "Mentone"
    club_id = "club_mentone"
    return club_name, club_id

def classify_team(name):
    """Classify team type and gender based on name."""
    name_lower = name.lower()

    # --- Type Classification ---
    if "midweek" in name_lower or "masters" in name_lower:
        team_type = "Midweek"
    elif "junior" in name_lower or any(f"u{age}" in name_lower for age in range(8, 19)):
        team_type = "Junior"
    elif "senior" in name_lower or "pennant" in name_lower or "vic league" in name_lower:
        team_type = "Senior"
    else:
        team_type = "Senior"  # Default

    # --- Gender Classification ---
    if "women" in name_lower or "girls" in name_lower:
        gender = "Women"
    elif "men" in name_lower or "boys" in name_lower:
        gender = "Men"
    elif "mixed" in name_lower:
        gender = "Mixed"
    else:
        gender = "Men"  # Default

    return team_type, gender

def init_firebase():
    """Initialize Firebase connection."""
    try:
        if not firebase_admin._apps:
            potential_paths = [
                os.path.join(os.path.dirname(__file__), '..', 'secrets', 'serviceAccountKey.json'),
                os.path.join('secrets', 'serviceAccountKey.json'),
                os.path.join('backend', 'secrets', 'serviceAccountKey.json')
            ]

            for cred_path in potential_paths:
                if os.path.exists(cred_path):
                    cred = credentials.Certificate(cred_path)
                    firebase_admin.initialize_app(cred)
                    logger.info(f"Firebase initialized using: {cred_path}")
                    return firestore.client()
            raise FileNotFoundError("Cannot find serviceAccountKey.json")
        else:
            logger.info("Firebase app already initialized.")
            return firestore.client()
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")
        raise e

def find_mentone_teams_in_grade(grade_url, grade_data):
    """Find all Mentone teams on a grade page."""
    logger.info(f"Scanning grade: {grade_data['name']} (ID: {grade_data['id']})")

    response = make_request(grade_url)
    if not response:
        logger.warning(f"Failed to fetch grade page {grade_url}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    mentone_teams = []

    # Find all team links on page
    team_links = soup.select("a[href*='/games/team/']")
    logger.debug(f"Found {len(team_links)} team links on page")

    for link in team_links:
        href = link.get('href', '')
        team_name = link.text.strip()

        # Only process Mentone teams
        if TEAM_FILTER_KEYWORD.lower() not in team_name.lower():
            continue

        # Extract team ID
        team_match = TEAM_ID_REGEX.search(href)
        if team_match:
            comp_id, team_id = team_match.groups()
            mentone_teams.append({
                'id': team_id,
                'name': team_name,
                'url': urljoin(HV_BASE, href),
                'comp_id': comp_id
            })
            logger.debug(f"Found Mentone team: {team_name} (ID: {team_id})")

    if mentone_teams:
        logger.info(f"Found {len(mentone_teams)} Mentone teams in grade {grade_data['id']}")
    else:
        logger.info(f"No Mentone teams found in grade {grade_data['id']}")

    return mentone_teams

def create_team(db, team_info, grade_data, comp_data):
    """Create a team document in Firestore."""
    team_id = team_info['id']
    team_name = team_info['name']

    logger.info(f"Processing team: {team_name} (ID: {team_id})")

    # Create team document reference
    team_ref = db.collection("teams").document(team_id)

    # Check if team already exists
    if team_ref.get().exists:
        logger.info(f"Team already exists: {team_name} (ID: {team_id}) - updating")

    # Get references
    fixture_id = grade_data['id']
    comp_id = team_info['comp_id']
    grade_ref = db.collection("grades").document(str(fixture_id))
    comp_ref = db.collection("competitions").document(str(comp_id))

    # Extract club info and create/get reference
    club_name, club_id = extract_club_info(team_name)
    club_ref = db.collection("clubs").document(club_id)

    # Create club if it doesn't exist
    if not club_ref.get().exists:
        club_data = {
            "id": club_id,
            "name": "Mentone Hockey Club",
            "short_name": "Mentone",
            "code": "MHC",
            "primary_color": "#4A90E2",
            "secondary_color": "#FFFFFF",
            "is_home_club": True,
            "active": True,
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP
        }
        club_ref.set(club_data)

    # Classify team
    team_type, gender = classify_team(grade_data.get('name', '') + ' ' + team_name)

    # Get season from grade or competition data
    season = grade_data.get('season', comp_data.get('season', '2025'))

    # Create proper comp_name
    comp_name = f"{grade_data.get('name', 'Unknown')} - {season}"

    # Create team data
    team_data = {
        "id": int(team_id),
        "name": team_name,
        "hv_team_id": int(team_id),
        "fixture_id": int(fixture_id),
        "comp_id": int(comp_id),
        "comp_name": comp_name,
        "grade_ref": grade_ref,
        "competition_ref": comp_ref,
        "type": team_type,
        "gender": gender,
        "club": club_name,
        "club_id": club_id,
        "club_ref": club_ref,
        "is_home_club": True,
        "season": season,
        "active": True,
        "url": team_info['url'],
        "updated_at": firestore.SERVER_TIMESTAMP,
        "last_checked": firestore.SERVER_TIMESTAMP,
        "mentone_playing": True  # Important for game filtering
    }

    # Add creation timestamp for new teams
    if not team_ref.get().exists:
        team_data["created_at"] = firestore.SERVER_TIMESTAMP
        team_data["ladder_position"] = None
        team_data["ladder_points"] = None
        team_data["ladder_updated_at"] = None

    # Save to Firestore
    team_ref.set(team_data, merge=True)

    return team_ref

def main():
    """Main function to scan all grades for Mentone teams."""
    logger.info("=== Finding All Mentone Teams ===")
    start_time = time.time()

    try:
        # Initialize Firestore
        db = init_firebase()

        # Get all existing grades from Firestore
        grades_query = db.collection("grades").where("active", "==", True).stream()
        grades = []

        for doc in grades_query:
            grade_data = doc.to_dict()
            grade_data['id'] = doc.id
            grades.append(grade_data)

        logger.info(f"Found {len(grades)} active grades in Firestore")

        # Get all existing competitions (we'll need their data)
        comps_dict = {}
        comps_query = db.collection("competitions").where("active", "==", True).stream()

        for doc in comps_query:
            comp_data = doc.to_dict()
            comps_dict[doc.id] = comp_data

        logger.info(f"Found {len(comps_dict)} active competitions in Firestore")

        # Track statistics
        total_teams_found = 0
        total_new_teams = 0
        total_grades_scanned = 0

        # Process each grade
        for grade_data in grades:
            total_grades_scanned += 1

            # Skip if no URL
            grade_url = grade_data.get('url')
            if not grade_url:
                logger.warning(f"Grade {grade_data['id']} ({grade_data.get('name', 'Unknown')}) has no URL - skipping")
                continue

            # Find Mentone teams in this grade
            teams = find_mentone_teams_in_grade(grade_url, grade_data)
            total_teams_found += len(teams)

            # Process each team
            for team_info in teams:
                comp_id = team_info['comp_id']
                comp_data = comps_dict.get(comp_id, {})

                # Get existing team count
                team_ref = db.collection("teams").document(team_info['id'])
                team_exists = team_ref.get().exists

                # Create or update team
                create_team(db, team_info, grade_data, comp_data)

                if not team_exists:
                    total_new_teams += 1

            # Small delay to be nice to the server
            time.sleep(0.1)

        elapsed_time = time.time() - start_time

        # Print summary
        logger.info("=== Scan Complete ===")
        logger.info(f"Scanned {total_grades_scanned} grades")
        logger.info(f"Found {total_teams_found} Mentone teams")
        logger.info(f"Created {total_new_teams} new team documents")
        logger.info(f"Script completed in {elapsed_time:.2f} seconds")

    except Exception as e:
        logger.error(f"Error during execution: {e}", exc_info=True)

if __name__ == "__main__":
    main()