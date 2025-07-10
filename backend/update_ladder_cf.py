"""
Cloud Function to update Hockey Victoria ladder positions for teams in Firestore.
"""
import json
import re
import time
from datetime import datetime

import firebase_admin
import requests
import pytz 
from bs4 import BeautifulSoup
from firebase_functions import https_fn
from firebase_admin import initialize_app, firestore

# --- Global Variables & Constants ---
try:
    firebase_admin.get_app()
except ValueError:
    initialize_app()

BASE_URL = "https://www.hockeyvictoria.org.au"
LADDER_URL_TEMPLATE = "https://www.hockeyvictoria.org.au/pointscore/{comp_id}/{fixture_id}"
DELAY_BETWEEN_REQUESTS_CF = 0.25  # seconds
AUSTRALIA_TZ = pytz.timezone("Australia/Melbourne")

# --- CORS Headers ---
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS", # Allow POST for triggering updates
    "Access-Control-Allow-Headers": "Content-Type",
}

# --- Logging Setup (Simplified) ---
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- Utility Functions (Adapted or Inlined) ---
def make_request_cf(url, session=None, timeout=10):
    requester = session if session else requests.Session()
    try:
        response = requester.get(url, timeout=timeout)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for {url}: {e}")
        return None

def clean_text_cf(text):
    if text is None: return ""
    return text.strip().replace('\n', ' ').replace('\r', ' ')

def extract_number_cf(text, default=0):
    if text is None: return default
    # Handle potential negative numbers for goal difference
    text_cleaned = str(text).strip()
    is_negative = text_cleaned.startswith('−') or text_cleaned.startswith('-')
    
    match = re.search(r'\d+', text_cleaned)
    if not match: return default
    
    number = int(match.group(0))
    return -number if is_negative else number


# --- Core Logic Functions (from update_ladder.py, adapted for CF) ---

def scrape_ladder_for_team_cf(team_details, session_obj):
    """
    Scrapes the ladder page for a specific team to get its position and stats.
    team_details: Dict containing comp_id, fixture_id, id (team's Firestore ID), name.
    session_obj: requests.Session object.
    """
    comp_id = team_details.get("comp_id")
    fixture_id = team_details.get("fixture_id")
    team_firestore_id = team_details.get("id") # Firestore document ID of the team
    team_name_from_db = team_details.get("name", "Unknown Team") # Name from our DB

    if not comp_id or not fixture_id:
        logger.error(f"Team {team_name_from_db} ({team_firestore_id}): Missing comp_id ('{comp_id}') or fixture_id ('{fixture_id}') for HV URL.")
        return None

    ladder_url = LADDER_URL_TEMPLATE.format(comp_id=comp_id, fixture_id=fixture_id)
    logger.info(f"Team {team_name_from_db} ({team_firestore_id}): Getting ladder from HV URL: {ladder_url}")

    response = make_request_cf(ladder_url, session=session_obj)
    if not response:
        logger.error(f"Team {team_name_from_db} ({team_firestore_id}): Failed to get ladder page: {ladder_url}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    ladder_table = soup.select_one("table.table")
    if not ladder_table:
        logger.warning(f"Team {team_name_from_db} ({team_firestore_id}): No ladder table found at: {ladder_url}")
        return None

    # Team name to search for in the ladder table can be tricky.
    # Try matching based on a simplified version of the team name from DB or keywords.
    search_term = "mentone" if "mentone" in team_name_from_db.lower() else team_name_from_db.lower().split(" - ")[0] # Basic heuristic

    extracted_data = {
        "id": team_firestore_id, # For updating the correct Firestore doc
        "ladder_position": None, "ladder_points": None, "ladder_stats": {},
        "ladder_updated_at": datetime.now(AUSTRALIA_TZ).astimezone(pytz.utc)
    }

    rows = ladder_table.select("tbody tr")
    for row_idx, row in enumerate(rows):
        cells = row.select("td")
        if not cells: continue

        team_cell_text = clean_text_cf(cells[0].text).lower()
        
        # Check if this row's team name matches our target team
        # This needs to be robust: HV names can vary slightly.
        # Using 'search_term' or comparing with known HV team ID if available & matched during team discovery.
        # For now, relying on 'mentone' keyword for Mentone teams or partial name match.
        # A more robust match would involve hv_team_id if we stored that during team discovery.
        if search_term in team_cell_text or team_name_from_db.lower() in team_cell_text:
            logger.debug(f"Team {team_name_from_db}: Found potential match in row {row_idx+1}: '{cells[0].text.strip()}'")
            
            position_match = re.match(r'(\d+)\.?', cells[0].text.strip())
            extracted_data["ladder_position"] = int(position_match.group(1)) if position_match else (row_idx + 1)

            # Extract stats based on typical column order
            # P W D L F A GD Pts
            if len(cells) > 9: # Need at least 10 columns for typical full stats
                extracted_data["ladder_stats"]["games_played"] = extract_number_cf(cells[1].text, 0)
                extracted_data["ladder_stats"]["wins"] = extract_number_cf(cells[2].text, 0)
                extracted_data["ladder_stats"]["draws"] = extract_number_cf(cells[3].text, 0)
                extracted_data["ladder_stats"]["losses"] = extract_number_cf(cells[4].text, 0)
                # Column 5 is often Byes or Forfeits - skipping for now unless specifically needed
                extracted_data["ladder_stats"]["goals_for"] = extract_number_cf(cells[6].text, 0)
                extracted_data["ladder_stats"]["goals_against"] = extract_number_cf(cells[7].text, 0)
                extracted_data["ladder_stats"]["goal_difference"] = extract_number_cf(cells[8].text, 0) # GD
                extracted_data["ladder_points"] = extract_number_cf(cells[9].text, 0) # Points
            elif len(cells) > 1: # Simplified ladder, might only have points
                 extracted_data["ladder_points"] = extract_number_cf(cells[-1].text, 0) # Assume points is last column

            logger.info(f"Team {team_name_from_db} ({team_firestore_id}): Extracted - Pos: {extracted_data['ladder_position']}, Pts: {extracted_data['ladder_points']}")
            return extracted_data # Found our team

    logger.warning(f"Team {team_name_from_db} ({team_firestore_id}): Not found in ladder table at {ladder_url} using search term '{search_term}'.")
    return None


def update_team_in_firestore_cf(db_client, team_ladder_data, dry_run_mode):
    """Updates a team's ladder info in Firestore."""
    team_firestore_id = team_ladder_data["id"]
    team_ref = db_client.collection("teams").document(team_firestore_id)

    update_payload = {
        "ladder_position": team_ladder_data.get("ladder_position"),
        "ladder_points": team_ladder_data.get("ladder_points"),
        "ladder_stats": team_ladder_data.get("ladder_stats", {}), # Ensure stats field is present
        "ladder_updated_at": team_ladder_data.get("ladder_updated_at", datetime.now(AUSTRALIA_TZ).astimezone(pytz.utc))
    }
    # Filter out None values from payload to avoid overwriting existing good data with None
    update_payload = {k: v for k, v in update_payload.items() if v is not None}
    if not update_payload.get("ladder_stats"): # If stats is empty, remove it
        update_payload.pop("ladder_stats", None)


    if dry_run_mode:
        logger.info(f"[DRY RUN] Team {team_firestore_id}: Would update with: {update_payload}")
        return True
    
    if not update_payload or update_payload.get("ladder_position") is None: # Basic check
        logger.warning(f"Team {team_firestore_id}: No valid ladder data to update. Payload: {update_payload}")
        return False

    try:
        team_ref.update(update_payload)
        logger.info(f"Team {team_firestore_id}: Firestore updated with ladder data.")
        return True
    except Exception as e_save:
        logger.error(f"Team {team_firestore_id}: Failed to update Firestore: {e_save}", exc_info=True)
        return False

# --- Cloud Function Entry Point ---
@https_fn.on_request()
def update_ladder_cf(req: https_fn.Request) -> https_fn.Response:
    if req.method == 'OPTIONS': # Handle CORS preflight
        return https_fn.Response("", status=204, headers=CORS_HEADERS)

    log_level_param = req.args.get("log_level", "INFO").upper()
    logger.setLevel(getattr(logging, log_level_param, logging.INFO))
    logger.info(f"update_ladder_cf triggered. Log level: {log_level_param}. Method: {req.method}")

    db = firestore.client()
    session = requests.Session()

    # Request Parameters
    team_id_param = req.args.get("team_id") # Firestore team document ID to update a single team
    comp_id_param = req.args.get("comp_id") # Alternative: update all teams in a competition
    # fixture_id_param = req.args.get("fixture_id") # Or specific grade/fixture
    mentone_teams_only_param = req.args.get("mentone_only", "true").lower() == "true" # Default to Mentone teams if no specific target
    limit_teams_param = req.args.get("limit_teams", type=int, default=0) # 0 for no limit if processing multiple
    dry_run_param = req.args.get("dry_run", "false").lower() == "true"
    
    teams_to_query = []
    try:
        teams_collection = db.collection("teams")
        if team_id_param:
            logger.info(f"Fetching specific team by Firestore ID: {team_id_param}")
            team_doc = teams_collection.document(team_id_param).get()
            if team_doc.exists:
                teams_to_query.append({"id": team_doc.id, **team_doc.to_dict()})
            else:
                return https_fn.Response(json.dumps({"status":"error", "message":f"Team with Firestore ID {team_id_param} not found."}),
                                       status=404, mimetype="application/json", headers=CORS_HEADERS)
        elif comp_id_param:
            logger.info(f"Fetching teams for Competition ID: {comp_id_param}. Mentone only: {mentone_teams_only_param}")
            query = teams_collection.where("comp_id", "==", str(comp_id_param))
            if mentone_teams_only_param: query = query.where("is_home_club", "==", True)
            if limit_teams_param > 0: query = query.limit(limit_teams_param)
            for team_doc in query.stream():
                teams_to_query.append({"id": team_doc.id, **team_doc.to_dict()})
        else: # Default: Mentone teams (or all if mentone_only=false)
            logger.info(f"Fetching teams. Mentone only: {mentone_teams_only_param}. Limit: {limit_teams_param}")
            query = teams_collection
            if mentone_teams_only_param: query = query.where("is_home_club", "==", True)
            if limit_teams_param > 0: query = query.limit(limit_teams_param)
            for team_doc in query.stream():
                teams_to_query.append({"id": team_doc.id, **team_doc.to_dict()})
        
        # Filter out teams that don't have comp_id or fixture_id, as they can't be processed
        valid_teams_to_process = [
            t for t in teams_to_query if t.get("comp_id") and t.get("fixture_id")
        ]
        if len(valid_teams_to_process) != len(teams_to_query):
            logger.warning(f"Filtered out {len(teams_to_query) - len(valid_teams_to_process)} teams due to missing comp_id or fixture_id.")

        if not valid_teams_to_process:
            return https_fn.Response(json.dumps({"status":"success", "message":"No valid teams found to process based on parameters."}),
                                   status=200, mimetype="application/json", headers=CORS_HEADERS)
        
        logger.info(f"Processing {len(valid_teams_to_process)} teams. Dry run: {dry_run_param}")
        
        teams_updated_count = 0
        teams_failed_scrape_count = 0
        teams_failed_firestore_count = 0
        start_time_overall = time.time()

        for i, team_data_from_db in enumerate(valid_teams_to_process):
            team_name_log = team_data_from_db.get('name', team_data_from_db.get('id'))
            logger.info(f"Processing team {i+1}/{len(valid_teams_to_process)}: {team_name_log}")
            
            ladder_info = scrape_ladder_for_team_cf(team_data_from_db, session)
            if ladder_info:
                if update_team_in_firestore_cf(db, ladder_info, dry_run_param):
                    teams_updated_count += 1
                else:
                    teams_failed_firestore_count += 1
            else:
                teams_failed_scrape_count += 1
            
            if i < len(valid_teams_to_process) - 1: # If not the last team
                time.sleep(DELAY_BETWEEN_REQUESTS_CF)

        duration_overall = time.time() - start_time_overall
        summary_msg = (
            f"Ladder update process finished in {duration_overall:.2f}s. "
            f"Teams targeted: {len(valid_teams_to_process)}. "
            f"Successfully updated: {teams_updated_count}. "
            f"Failed to scrape: {teams_failed_scrape_count}. Failed to save: {teams_failed_firestore_count}."
        )
        logger.info(summary_msg)
        if dry_run_param: logger.info("DRY RUN active. No actual database writes occurred.")

        return https_fn.Response(
            json.dumps({
                "status": "success", "message": summary_msg,
                "data": {
                    "teams_targeted_for_update": len(valid_teams_to_process),
                    "teams_successfully_updated": teams_updated_count,
                    "teams_failed_scrape": teams_failed_scrape_count,
                    "teams_failed_firestore_update": teams_failed_firestore_count,
                    "duration_seconds": round(duration_overall, 2),
                    "dry_run": dry_run_param
                }
            }),
            status=200, mimetype="application/json", headers=CORS_HEADERS
        )

    except Exception as e_main_handler:
        logger.error(f"Critical error in update_ladder_cf main handler: {str(e_main_handler)}", exc_info=True)
        return https_fn.Response(
            json.dumps({"status": "error", "message": f"Critical error: {str(e_main_handler)}"}),
            status=500, mimetype="application/json", headers=CORS_HEADERS
        )
