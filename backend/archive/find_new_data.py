# add_new_data_ladder_focused.py
#
# Purpose: Adds new competitions, grades, and Mentone teams incrementally.
#          Uses Ladder pages for reliable team discovery.
#          Optimized to only scan grades if new or not checked recently.
#          Uses Firestore native IDs.

import firebase_admin
from firebase_admin import credentials, firestore
import requests
from bs4 import BeautifulSoup
import re
import json
import logging
import time
from urllib.parse import urljoin
from datetime import datetime, timedelta, timezone
import os

# --- Basic Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s [%(funcName)s] - %(message)s',
    handlers=[
        logging.FileHandler(f"add_new_data_ladder_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Constants ---
BASE_URL = "https://www.revolutionise.com.au/vichockey/games/"
HV_BASE = "https://www.hockeyvictoria.org.au"
TEAM_FILTER_KEYWORD = "Mentone"
REQUEST_TIMEOUT = 15
MAX_RETRIES = 3
RETRY_DELAY = 3
SCRIPT_VERSION = "2.2-ladder-focused"
GRADE_RECHECK_THRESHOLD_HOURS = 24 * 7 # Re-check grades once a week
MAX_BATCH_SIZE = 400 # Firestore batch limit

# --- Regex Patterns ---
COMP_FIXTURE_REGEX = re.compile(r"/games/(\d+)/(\d+)") # comp_id, fixture_id
TEAM_ID_REGEX = re.compile(r"/games/team/(\d+)/(\d+)") # comp_id, team_id
GAME_ID_REGEX = re.compile(r'/game/(\d+)$')
PARENT_COMP_ID_REGEX = re.compile(r'/(?:reports/games|team-stats)/(\d+)') # Extracts ID from action links

# --- Classification Maps ---
GENDER_MAP = {"men": "Men", "women": "Women", "boys": "Boys", "girls": "Girls", "mixed": "Mixed"}
TYPE_KEYWORDS = {"senior": "Senior", "junior": "Junior", "midweek": "Midweek", "masters": "Masters", "outdoor": "Outdoor", "indoor": "Indoor"}

# --- Firebase Initialization ---
try:
    if not firebase_admin._apps:
        cred_path = os.path.join(os.path.dirname(__file__), '..', 'secrets', 'serviceAccountKey.json')
        if not os.path.exists(cred_path): cred_path = os.path.join('../secrets', 'serviceAccountKey.json')
        if not os.path.exists(cred_path): raise FileNotFoundError("Cannot find serviceAccountKey.json")
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        logger.info(f"Firebase initialized using: {cred_path}")
    else: logger.info("Firebase app already initialized.")
    db = firestore.client()
except Exception as e:
    logger.error(f"Failed to initialize Firebase: {e}", exc_info=True)
    exit(1)

# ==================================
# Helper Functions (Keep as they are generally useful)
# ==================================
def make_request(url, retry_count=0):
    """Make an HTTP request with retries and error handling."""
    try:
        logger.debug(f"Requesting: {url}")
        response = requests.get(url, timeout=REQUEST_TIMEOUT, headers={'User-Agent': f'MentoneHockeyApp-Incremental/{SCRIPT_VERSION}'})
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        if retry_count < MAX_RETRIES:
            wait_time = RETRY_DELAY * (retry_count + 1)
            logger.warning(f"Request to {url} failed: {e}. Retrying ({retry_count+1}/{MAX_RETRIES}) in {wait_time}s...")
            time.sleep(wait_time); return make_request(url, retry_count + 1)
        else: logger.error(f"Request to {url} failed after {MAX_RETRIES} attempts: {e}"); return None

# --- Corrected extract_club_info ---
def extract_club_info(team_name_text):
    """Extracts club name, using 'mentone' specifically for Mentone club_id."""
    # --- Club Name Extraction ---
    club_name = None
    # Prioritize finding the exact keyword case-insensitively
    if TEAM_FILTER_KEYWORD.lower() in team_name_text.lower():
        club_name = TEAM_FILTER_KEYWORD # Use the canonical "Mentone"
    else:
        # Fallback logic for non-Mentone clubs
        parts = team_name_text.split(" - ")
        if len(parts) > 1:
            # Basic check if first part looks like a club (avoids grabbing grade info)
            if "hockey club" in parts[0].lower() or "hc" in parts[0].lower() or len(parts[0].split()) <= 3 : # Heuristic: club names are usually short
                club_name = parts[0].strip()
            else: # If first part seems too long, maybe the team name format is different
                club_name = team_name_text.split()[0] # Default to first word
                logger.debug(f"Complex team name '{team_name_text}', using first word '{club_name}' as club name.")
        else:
            club_name = team_name_text.split()[0] # Default to first word if no " - "
        logger.debug(f"Non-Mentone club detected/inferred: '{club_name}' from '{team_name_text}'")

    # --- Club ID Generation ---
    if club_name.lower() == TEAM_FILTER_KEYWORD.lower():
        club_id = "mentone" # *** USE 'mentone' SPECIFICALLY ***
    else:
        # Generate ID for other clubs
        base_id = club_name.lower().replace(" ", "_").replace("-", "_").replace("'", "").replace(".", "")
        # Decide on prefixing for non-mentone clubs (optional)
        # club_id = f"club_{base_id}" # Option 1: Keep prefix for others
        club_id = base_id       # Option 2: No prefix for others either

    return club_name, club_id

def get_or_create_club(club_name, club_id, batch=None):
    """Creates or gets a club document. Optionally uses a batch for write."""
    club_ref = db.collection("clubs").document(club_id); is_mentone = TEAM_FILTER_KEYWORD.lower() in club_name.lower()
    try:
        club_doc = club_ref.get()
        if not club_doc.exists:
            logger.info(f"Creating new club: {club_name} ({club_id})")
            club_data = { "id": club_id, "name": club_name if not is_mentone else f"{TEAM_FILTER_KEYWORD} Hockey Club", "short_name": club_name.replace(" Hockey Club", "").strip(), "code": "".join([word[0] for word in club_name.split() if word[0].isalpha()]).upper()[:3], "location": "Mentone, Victoria" if is_mentone else None, "home_venue": "Mentone Grammar Playing Fields" if is_mentone else None, "primary_color": "#4A90E2" if is_mentone else "#333333", "secondary_color": "#FFFFFF", "active": True, "created_at": firestore.SERVER_TIMESTAMP, "updated_at": firestore.SERVER_TIMESTAMP, "is_home_club": is_mentone, "last_checked": firestore.SERVER_TIMESTAMP }
            if batch: batch.set(club_ref, club_data)
            else: club_ref.set(club_data)
            return club_ref, True
        else:
            update_data = { "last_checked": firestore.SERVER_TIMESTAMP, "updated_at": firestore.SERVER_TIMESTAMP }
            if batch: batch.update(club_ref, update_data)
            else: club_ref.update(update_data)
            return club_ref, False
    except Exception as e: logger.error(f"Error creating/getting club '{club_id}': {e}"); return club_ref, False

def classify_item(name):
    """Classifies competition, grade, or team name by type and gender."""
    # ... (Keep this function as is) ...
    name_lower = name.lower(); team_type = "Unknown"; gender = "Unknown"
    if "midweek" in name_lower or "masters" in name_lower or any(f"{age}+" in name_lower for age in [35, 45, 50, 60, 70]): team_type = "Midweek"
    elif "junior" in name_lower or any(f"u{age}" in name_lower for age in range(8, 19)): team_type = "Junior"
    elif "senior" in name_lower or "pennant" in name_lower or "vic league" in name_lower or "premier league" in name_lower or "metro" in name_lower: team_type = "Senior"
    elif "indoor" in name_lower: team_type = "Indoor"
    elif "outdoor" in name_lower: team_type = "Outdoor"
    elif "social" in name_lower or "summer" in name_lower or "vaisakhi" in name_lower or "cup" in name_lower: team_type = "Social/Other"
    if team_type == "Unknown":
        for keyword, value in TYPE_KEYWORDS.items():
            if keyword in name_lower: team_type = value; break
    if team_type == "Unknown": team_type = "Senior"
    if "women" in name_lower or "girls" in name_lower or "ladies" in name_lower: gender = "Women"
    elif "men" in name_lower or "boys" in name_lower: gender = "Men"
    elif "mixed" in name_lower: gender = "Mixed"
    if gender == "Unknown":
        for keyword, value in GENDER_MAP.items():
            if keyword in name_lower: gender = value; break
    if gender == "Unknown":
        if team_type == "Junior": gender = "Mixed"
        elif team_type == "Midweek" and "women" not in name_lower: gender = "Men"
        elif team_type == "Senior" and "women" not in name_lower: gender = "Men"
    return team_type, gender

def is_valid_team(name):
    """Filter out false positives like venue names."""
    invalid_keywords = ["playing fields", "grammar", "venue", "park", "centre", "school", "hockey victoria"]
    return all(kw not in name.lower() for kw in invalid_keywords) # Simpler check


# ==================================
# NEW Scraping & Processing Logic
# ==================================

def scrape_and_process_main_page(db):
    """
    Scrapes HV Games page, identifies structure, creates/updates comps & grades in Firestore.
    Returns a list of tuples: [(grade_info, grade_ref, parent_comp_ref), ...] for grades needing team scan.
    """
    logger.info(f"Scraping main games page: {BASE_URL}")
    response = make_request(BASE_URL)
    if not response: return []

    soup = BeautifulSoup(response.text, "html.parser")
    comp_start_divs = soup.select("div.p-4.d-md-flex.align-items-center.justify-content-between")
    if not comp_start_divs:
        logger.error("Could not find competition starting divs. Scraping structure likely changed.")
        return []

    logger.info(f"Found {len(comp_start_divs)} potential parent competition blocks.")
    grades_to_scan_teams_for = []
    now_utc = datetime.now(timezone.utc)
    recheck_grade_threshold_utc = now_utc - timedelta(hours=GRADE_RECHECK_THRESHOLD_HOURS)

    # Use batching for efficiency during metadata updates
    metadata_batch = db.batch()
    metadata_batch_count = 0

    for start_div in comp_start_divs:
        heading_tag = start_div.select_one("h2.h4")
        if not heading_tag: continue
        heading_text = heading_tag.text.strip()

        # Extract parent_comp_id from action links
        parent_comp_id = None
        for link in start_div.select("div.btn-group a[href]"):
            id_match = PARENT_COMP_ID_REGEX.search(link['href'])
            if id_match: parent_comp_id = id_match.group(1); break

        if not parent_comp_id:
            logger.error(f"Could not find parent_comp_id for competition '{heading_text}'. Skipping this block.")
            continue

        logger.debug(f"Processing Competition Block: {heading_text} (Parent ID: {parent_comp_id})")

        # --- Process Parent Competition ---
        comp_doc_id = str(parent_comp_id)
        comp_ref = db.collection("competitions").document(comp_doc_id)
        comp_doc = comp_ref.get()
        year_match = re.search(r'\b(20\d{2})\b', heading_text)
        season = year_match.group(1) if year_match else str(datetime.now().year)
        comp_type, _ = classify_item(heading_text)

        if not comp_doc.exists:
            logger.info(f"Creating PARENT Competition: {heading_text} (ID: {comp_doc_id})")
            comp_data = { "id": int(parent_comp_id), "name": heading_text, "season": season, "type": comp_type, "active": True, "created_at": firestore.SERVER_TIMESTAMP, "updated_at": firestore.SERVER_TIMESTAMP, "last_checked": firestore.SERVER_TIMESTAMP }
            metadata_batch.set(comp_ref, comp_data)
            metadata_batch_count += 1
        else:
            logger.debug(f"Updating PARENT Competition: {heading_text} (ID: {comp_doc_id})")
            comp_update = { "name": heading_text, "season": season, "type": comp_type, "active": True, "updated_at": firestore.SERVER_TIMESTAMP, "last_checked": firestore.SERVER_TIMESTAMP }
            metadata_batch.update(comp_ref, comp_update)
            metadata_batch_count += 1

        # --- Process Grades Under This Parent ---
        current_element = start_div.find_next_sibling()
        while current_element:
            # Stop if we hit the start of the NEXT competition block
            if current_element.name == 'div' and current_element.select_one("h2.h4"): break

            # Check if it's a grade link div
            if current_element.name == 'div' and 'px-4' in current_element.get('class', []):
                link_tag = current_element.find('a')
                if link_tag and link_tag.get('href'):
                    href = link_tag['href']
                    match = COMP_FIXTURE_REGEX.search(href)
                    if match:
                        comp_id_from_link, fixture_id = match.groups()
                        grade_name = link_tag.text.strip()
                        grade_url = urljoin(HV_BASE, href)

                        # --- Process Grade ---
                        grade_doc_id = str(fixture_id)
                        grade_ref = db.collection("grades").document(grade_doc_id)
                        grade_doc = grade_ref.get()
                        grade_type, gender = classify_item(grade_name)
                        grade_season = season # Default to parent season

                        grade_payload = { "id": int(fixture_id), "name": grade_name, "fixture_id": int(fixture_id), "comp_id": int(comp_id_from_link), "parent_comp_ref": comp_ref, "url": grade_url, "type": grade_type, "gender": gender, "season": grade_season, "active": True, "updated_at": firestore.SERVER_TIMESTAMP, "last_checked": firestore.SERVER_TIMESTAMP }

                        should_scan_this_grade = False
                        if not grade_doc.exists:
                            logger.info(f"Creating GRADE: {grade_name} (ID: {grade_doc_id})")
                            grade_payload["created_at"] = firestore.SERVER_TIMESTAMP
                            metadata_batch.set(grade_ref, grade_payload)
                            metadata_batch_count += 1
                            should_scan_this_grade = True # Scan new grades
                        else:
                            logger.debug(f"Updating GRADE: {grade_name} (ID: {grade_doc_id})")
                            existing_grade_data = grade_doc.to_dict()
                            metadata_batch.update(grade_ref, {k: v for k, v in grade_payload.items() if k not in ["id", "created_at"]})
                            metadata_batch_count += 1
                            # Check if existing grade needs re-scan
                            last_checked_dt = existing_grade_data.get('last_checked')
                            if isinstance(last_checked_dt, datetime):
                                if last_checked_dt.tzinfo is None: last_checked_dt = last_checked_dt.replace(tzinfo=timezone.utc)
                                if last_checked_dt < recheck_grade_threshold_utc: should_scan_this_grade = True
                            else: should_scan_this_grade = True # Scan if missing timestamp

                        if should_scan_this_grade:
                            grade_info = {"fixture_id": fixture_id, "comp_id": comp_id_from_link, "name": grade_name, "url": grade_url}
                            grades_to_scan_teams_for.append((grade_info, grade_ref, comp_ref))
                            logger.info(f"Marked Grade {fixture_id} ('{grade_name}') for team scan.")
                        else:
                            logger.debug(f"Skipping team scan for recently checked grade {fixture_id} ('{grade_name}')")

                        # Commit metadata batch periodically
                        if metadata_batch_count >= MAX_BATCH_SIZE:
                            logger.info(f"Committing metadata batch ({metadata_batch_count} operations)...")
                            metadata_batch.commit()
                            metadata_batch = db.batch(); metadata_batch_count = 0

            current_element = current_element.find_next_sibling() # Move to next element

    # Commit any remaining metadata operations
    if metadata_batch_count > 0:
        logger.info(f"Committing final metadata batch ({metadata_batch_count} operations)...")
        metadata_batch.commit()

    logger.info(f"Finished processing metadata. Identified {len(grades_to_scan_teams_for)} grades needing team scan.")
    return grades_to_scan_teams_for

def find_teams_on_ladder_page(grade_info, grade_ref, parent_comp_ref):
    """Scrapes the LADDER page for Mentone teams and their IDs."""
    # ... (This function remains unchanged) ...
    fixture_id = grade_info['fixture_id']; comp_id = grade_info['comp_id']; grade_name = grade_info['name']
    ladder_url = f"{HV_BASE}/pointscore/{comp_id}/{fixture_id}"
    logger.info(f"Scanning LADDER page for Mentone teams: {grade_name} (Fixture: {fixture_id}) at {ladder_url}")
    response = make_request(ladder_url)
    if not response: logger.warning(f"Failed to fetch LADDER page {ladder_url}."); return []
    soup = BeautifulSoup(response.text, "html.parser"); mentone_teams_found = []
    ladder_table = soup.select_one("table.table.table-hover")
    if not ladder_table: logger.warning(f"Could not find ladder table on {ladder_url}."); return []
    rows = ladder_table.select("tbody tr"); logger.debug(f"Found {len(rows)} rows in ladder table for grade {fixture_id}")
    for row in rows:
        first_cell = row.select_one("td"); link_tag = first_cell.select_one("a[href*='/games/team/']") if first_cell else None
        if link_tag:
            href = link_tag.get('href', ''); team_name_text = link_tag.text.strip()
            if TEAM_FILTER_KEYWORD.lower() in team_name_text.lower():
                team_match = TEAM_ID_REGEX.search(href)
                if team_match: link_comp_id, actual_team_id = team_match.groups(); logger.debug(f"Found Mentone team on ladder: '{team_name_text}' (ID: {actual_team_id})"); mentone_teams_found.append((actual_team_id, team_name_text))
                else: logger.warning(f"Found Mentone text '{team_name_text}' but failed to extract ID from href: {href}")
    if not mentone_teams_found: logger.info(f"No Mentone teams found in ladder table for grade {fixture_id}.")
    else: logger.info(f"Found {len(mentone_teams_found)} Mentone team(s) in ladder table for grade {fixture_id}.")
    return mentone_teams_found


def process_team(db, team_id, team_name_from_link, grade_ref, parent_comp_ref, batch):
    """
    Creates or updates a team document using the actual team_id as doc_id.
    Aligns fields with the desired schema (string 'id', numeric IDs, descriptive name).
    Returns tuple of (team_ref, was_created).
    """
    doc_id = str(team_id) # Use string HV ID as Firestore Document ID
    team_ref = db.collection("teams").document(doc_id)

    try:
        team_doc = team_ref.get(); exists = team_doc.exists

        # Get grade data
        grade_data = grade_ref.get().to_dict() or {}
        fixture_id = grade_data.get('fixture_id') # Should be number
        comp_id = grade_data.get('comp_id')       # Should be number
        grade_name = grade_data.get('name', '')   # Full grade name (e.g., "Men's Pennant B - 2025")
        season = grade_data.get('season', str(datetime.now().year))

        # Extract club info (uses corrected extract_club_info -> 'Mentone', 'mentone')
        club_name, club_id = extract_club_info(team_name_from_link)
        club_ref, _ = get_or_create_club(club_name, club_id, batch) # Pass batch

        # Classify team based on grade info
        team_type, gender = classify_item(grade_name)

        # Construct descriptive team name
        grade_name_base = re.sub(r'\s*-\s*\d{4}$', '', grade_name).strip() # Remove " - YYYY" suffix
        descriptive_team_name = f"{club_name} - {grade_name_base}"

        # Create team URL
        team_url = f"{HV_BASE}/games/team/{comp_id}/{team_id}" if comp_id else None

        # --- Data Payload Alignment ---
        data_payload = {
            "id": doc_id, # *** STORE STRING ID MATCHING DOC ID ***
            # "hv_team_id": int(team_id), # Removed redundant field
            "name": descriptive_team_name, # *** USE DESCRIPTIVE NAME ***
            "fixture_id": fixture_id, # Use numeric from grade data
            "comp_id": comp_id,       # Use numeric from grade data
            "comp_name": grade_name, # *** USE FULL GRADE NAME ***
            "grade_ref": grade_ref,
            "competition_ref": parent_comp_ref,
            "type": team_type,
            "gender": gender,
            "club": f"{club_name} Hockey Club" if club_name == "Mentone" else club_name, # *** USE FULL CLUB NAME ***
            "club_id": club_id, # *** USE CORRECTED 'mentone' ID ***
            "club_ref": club_ref,
            "is_home_club": True,
            "season": season,
            "active": True,
            "url": team_url,
            "updated_at": firestore.SERVER_TIMESTAMP,
            "last_checked": firestore.SERVER_TIMESTAMP,
            "mentone_playing": True # Assume true if found via Mentone filter
        }

        was_created = False
        if not exists:
            logger.info(f"Creating team: {descriptive_team_name} (ID: {doc_id})")
            data_payload["created_at"] = firestore.SERVER_TIMESTAMP
            # Initialize ladder fields
            data_payload["ladder_position"] = None
            data_payload["ladder_points"] = None
            data_payload["ladder_updated_at"] = None
            batch.set(team_ref, data_payload) # Use batch
            was_created = True
        else:
            logger.debug(f"Updating team: {descriptive_team_name} (ID: {doc_id})")
            # Update relevant fields, ensuring 'id' matches doc_id (as string)
            update_data = {k: v for k, v in data_payload.items() if k not in [
                "created_at", "ladder_position", "ladder_points", "ladder_updated_at"
                # Keep 'id' in update payload to ensure it's the string version
            ]}
            batch.update(team_ref, update_data) # Use batch

        return team_ref, was_created
    except Exception as e:
        logger.error(f"Error processing team {doc_id} ('{team_name_from_link}'): {e}", exc_info=True)
        return team_ref, False

# ==================================
# Main Execution Logic
# ==================================
def main():
    start_time = time.time()
    logger.info(f"=== Mentone Hockey Club Add New Data (Incremental Ladder v{SCRIPT_VERSION}) ===")

    try:
        # 1. Scrape main page & Process Comp/Grade Metadata (get list of grades to scan)
        grades_to_scan = scrape_and_process_main_page(db)
        if not grades_to_scan:
            logger.warning("No grades identified for team scanning.")
            # Still proceed in case only metadata updates were needed

        # 2. Scan selected Grades for Teams and process them (Batched)
        logger.info(f"--- Scanning {len(grades_to_scan)} Grades for Mentone Teams ---")
        total_new_teams = 0
        scanned_grades_count = 0
        team_batch = db.batch()
        team_batch_count = 0

        for grade_info, grade_ref, parent_comp_ref in grades_to_scan:
            scanned_grades_count += 1
            # Find teams using the LADDER page now
            mentone_teams_on_ladder = find_teams_on_ladder_page(grade_info, grade_ref, parent_comp_ref)

            if mentone_teams_on_ladder:
                for team_id, team_name in mentone_teams_on_ladder:
                    # Process each found team (creates or updates in batch)
                    _, created_team = process_team(db, team_id, team_name, grade_ref, parent_comp_ref, team_batch)
                    if created_team:
                        total_new_teams += 1
                    # Increment count regardless of create/update for batch limit
                    team_batch_count += 1

                    # Commit batch periodically
                    if team_batch_count >= MAX_BATCH_SIZE:
                        logger.info(f"Committing team batch ({team_batch_count} operations)...")
                        team_batch.commit()
                        team_batch = db.batch(); team_batch_count = 0

            time.sleep(0.5) # Delay between scanning grade ladder pages

        # Commit any remaining team operations
        if team_batch_count > 0:
            logger.info(f"Committing final team batch ({team_batch_count} operations)...")
            team_batch.commit()

        # --- Final Summary ---
        logger.info("--- Scan Summary ---")
        logger.info(f"Processed metadata for competitions and grades found on main page.")
        logger.info(f"Scanned {scanned_grades_count} grade LADDER pages for teams (new or older than threshold).")
        logger.info(f"Added {total_new_teams} new Mentone teams.")

    except Exception as e:
        logger.error(f"An unexpected error occurred during the script: {e}", exc_info=True)

    elapsed_time = time.time() - start_time
    logger.info(f"Script finished in {elapsed_time:.2f} seconds.")

if __name__ == "__main__":
    main()