"""
Cloud Function to discover Hockey Victoria teams from ladder pages.
"""
import json
import re
import time
from datetime import datetime
from urllib.parse import urljoin

import firebase_admin
import requests
import pytz # For timezone handling
from bs4 import BeautifulSoup
from firebase_functions import https_fn
from firebase_admin import initialize_app, firestore

# --- Global Variables & Constants ---
try:
    firebase_admin.get_app()
except ValueError:
    initialize_app()

BASE_URL = "https://www.hockeyvictoria.org.au"
LADDER_URL_TEMPLATE = "https://www.hockeyvictoria.org.au/pointscore/{comp_id}/{fixture_id}" # fixture_id is grade_id
TEAM_URL_PATTERN = re.compile(r"/games/team/(\d+)/(\d+)") # Extracts comp_id and hv_team_id
DELAY_BETWEEN_REQUESTS_CF = 0.25  # seconds

AUSTRALIA_TZ = pytz.timezone("Australia/Melbourne")

# --- CORS Headers ---
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
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

def is_mentone_team_cf(team_name):
    if not team_name: return False
    return "mentone" in team_name.lower()

def determine_gender_cf(grade_name):
    grade_lower = grade_name.lower()
    if any(term in grade_lower for term in ["women's", "women", "female", "girls", "wom", "wg", "girl"]): return "Women"
    if any(term in grade_lower for term in ["men's", "men", "male", "boys", "boy", "mg"]): return "Men"
    if "mixed" in grade_lower or "mix" in grade_lower: return "Mixed"
    return "Unknown"

def determine_team_type_cf(grade_name):
    grade_lower = grade_name.lower()
    if any(term in grade_lower for term in ["junior", "under", "u10", "u12", "u14", "u16", "u18", "u19", "jnr"]): return "Junior"
    if any(term in grade_lower for term in ["senior", "premier", "vic league", "pennant", "metro", "snr"]): return "Senior"
    if any(term in grade_lower for term in ["master", "veteran", "35+", "40+", "45+", "50+", "mas"]): return "Masters"
    if "midweek" in grade_lower: return "Midweek"
    if "indoor" in grade_lower: return "Indoor"
    return "Senior" # Default

# --- Core Logic Functions (from discover_teams.py, adapted for CF) ---

def discover_teams_for_grade_cf(grade_details, session_obj):
    """
    Extracts teams from the ladder page of a specific grade.
    grade_details: Dict containing comp_id, id (fixture_id/grade_id), name.
    session_obj: requests.Session object.
    """
    comp_id = grade_details.get("comp_id")
    fixture_id = grade_details.get("id") # This is the grade's specific ID in HV system
    grade_name = grade_details.get("name", "Unknown Grade")

    if not comp_id or not fixture_id:
        logger.error(f"Grade {grade_name}: Missing comp_id ('{comp_id}') or fixture_id ('{fixture_id}')")
        return []

    ladder_url = LADDER_URL_TEMPLATE.format(comp_id=comp_id, fixture_id=fixture_id)
    logger.info(f"Grade {grade_name}: Discovering teams from HV URL: {ladder_url}")

    response = make_request_cf(ladder_url, session=session_obj)
    if not response:
        logger.error(f"Grade {grade_name}: Failed to get ladder page: {ladder_url}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    discovered_teams = []
    ladder_table = soup.select_one("table.table") # HV uses a simple class 'table'
    if not ladder_table:
        logger.warning(f"Grade {grade_name}: No ladder table found at: {ladder_url}")
        return []

    for row in ladder_table.select("tbody tr"):
        try:
            cells = row.select("td")
            if not cells: continue

            # Position and Team Name/Link are usually in the first cell
            position_cell = cells[0]
            pos_text = position_cell.text.strip()
            position = int(re.match(r"(\d+)\.?", pos_text).group(1)) if re.match(r"(\d+)\.?", pos_text) else None
            
            team_link_tag = position_cell.select_one("a[href*='/games/team/']")
            if not team_link_tag:
                logger.debug(f"Grade {grade_name}: No valid team link found in row: {pos_text}")
                continue

            team_name_scraped = clean_text_cf(team_link_tag.text)
            team_hv_url = urljoin(BASE_URL, team_link_tag.get("href", ""))
            
            team_url_match = TEAM_URL_PATTERN.search(team_hv_url)
            if not team_url_match:
                logger.warning(f"Grade {grade_name}: Could not extract HV team ID from URL '{team_hv_url}' for team '{team_name_scraped}'")
                continue
            # team_url_match.group(1) is comp_id, team_url_match.group(2) is hv_team_id
            hv_team_id = team_url_match.group(2) # This is the Hockey Victoria specific ID for the team

            # Extract detailed stats from table cells
            # Ensure enough cells exist, default to 0 if parsing fails
            s = { # s for stats
                "played": int(cells[1].text.strip()) if len(cells)>1 and cells[1].text.strip().isdigit() else 0,
                "wins": int(cells[2].text.strip()) if len(cells)>2 and cells[2].text.strip().isdigit() else 0,
                "draws": int(cells[3].text.strip()) if len(cells)>3 and cells[3].text.strip().isdigit() else 0,
                "losses": int(cells[4].text.strip()) if len(cells)>4 and cells[4].text.strip().isdigit() else 0,
                "byes": int(cells[5].text.strip()) if len(cells)>5 and cells[5].text.strip().isdigit() else 0,
                "goals_for": int(cells[6].text.strip()) if len(cells)>6 and cells[6].text.strip().isdigit() else 0,
                "goals_against": int(cells[7].text.strip()) if len(cells)>7 and cells[7].text.strip().isdigit() else 0,
                "goal_diff": int(cells[8].text.strip().replace('−','-')) if len(cells)>8 and cells[8].text.strip().replace('−','-').replace('-','').isdigit() else 0,
                "points": int(cells[9].text.strip()) if len(cells)>9 and cells[9].text.strip().isdigit() else 0,
            }

            is_mentone = is_mentone_team_cf(team_name_scraped)
            team_gender = determine_gender_cf(grade_name) # Infer from grade name
            team_category = determine_team_type_cf(grade_name) # Infer from grade name

            team_firestore_id = hv_team_id # Use HV Team ID as Firestore document ID for teams for consistency
            
            team_data = {
                "id": team_firestore_id, # HV Team ID
                "hv_id": hv_team_id, # Explicitly store HV team ID
                "name": f"Mentone - {grade_name}" if is_mentone else team_name_scraped, # Auto-prefix Mentone teams
                "short_name": "Mentone" if is_mentone else team_name_scraped.replace("Hockey Club", "").replace("Hockey Club", "").strip(),
                "club_name": "Mentone Hockey Club" if is_mentone else team_name_scraped.split(' - ')[0].strip(), # Best guess for club
                "is_home_club": is_mentone,
                "hv_url": team_hv_url,
                "comp_id": str(comp_id), # Store as string, matches other CFs
                "fixture_id": str(fixture_id), # Store as string
                "grade_name": grade_name, # Human readable name of the grade
                "ladder_position": position,
                "ladder_points": s["points"],
                "ladder_updated_at": datetime.now(AUSTRALIA_TZ).astimezone(pytz.utc),
                "type": team_category,
                "gender": team_gender,
                "active": True,
                "stats": s, # All ladder stats nested
                "updated_at": datetime.now(AUSTRALIA_TZ).astimezone(pytz.utc),
                # created_at will be handled by save function
                "competition_ref_str": f"competitions/{comp_id}", # String path for ref
                "grade_ref_str": f"grades/{fixture_id}", # String path for ref
            }
            discovered_teams.append(team_data)
        except Exception as e_row:
            logger.error(f"Grade {grade_name}: Error processing team row: {e_row}", exc_info=True)
            continue
    
    logger.info(f"Grade {grade_name}: Found {len(discovered_teams)} teams.")
    return discovered_teams

def save_team_cf(db_client, team_data, dry_run_mode):
    """Saves a team to Firestore. Uses hv_team_id as document ID."""
    team_firestore_id = str(team_data["id"]) # Should be hv_team_id
    team_ref = db_client.collection("teams").document(team_firestore_id)

    if dry_run_mode:
        logger.info(f"[DRY RUN] Would save team: {team_data.get('name')} (ID: {team_firestore_id})")
        return True
    
    try:
        now_utc = datetime.now(AUSTRALIA_TZ).astimezone(pytz.utc)
        team_data["updated_at"] = now_utc # Ensure update time is current
        
        existing_doc = team_ref.get()
        if existing_doc.exists:
            team_data["created_at"] = existing_doc.to_dict().get("created_at", now_utc)
        else:
            team_data["created_at"] = now_utc
        
        team_ref.set(team_data, merge=True) # Merge to preserve other fields if team doc has more structure
        logger.debug(f"Team {team_data.get('name')} (ID: {team_firestore_id}) saved successfully.")
        return True
    except Exception as e_save:
        logger.error(f"Failed to save team {team_data.get('name')} (ID: {team_firestore_id}): {e_save}", exc_info=True)
        return False

# --- Cloud Function Entry Point ---
@https_fn.on_request()
def discover_teams_cf(req: https_fn.Request) -> https_fn.Response:
    if req.method == 'OPTIONS':
        return https_fn.Response("", status=204, headers=CORS_HEADERS)

    log_level_param = req.args.get("log_level", "INFO").upper()
    logger.setLevel(getattr(logging, log_level_param, logging.INFO))
    logger.info(f"discover_teams_cf triggered. Log level: {log_level_param}")

    db = firestore.client()

    # Request Parameters
    comp_id_param = req.args.get("comp_id") # Process grades for a specific competition
    grade_id_param = req.args.get("grade_id") # Process a single specific grade (fixture_id)
    dry_run_param = req.args.get("dry_run", "false").lower() == "true"
    limit_grades_param = req.args.get("limit_grades", type=int)

    grades_to_process = []
    try:
        grades_collection = db.collection("grades")
        if grade_id_param: # Process a single grade
            logger.info(f"Fetching specific grade by ID: {grade_id_param}")
            grade_doc = grades_collection.document(str(grade_id_param)).get() # Ensure ID is string
            if grade_doc.exists:
                g_data = grade_doc.to_dict()
                # Ensure comp_id is present, as it's needed for URL
                if "comp_id" in g_data:
                    grades_to_process.append({"id": grade_doc.id, **g_data})
                else:
                    logger.error(f"Grade {grade_id_param} is missing 'comp_id' field.")
                    # Potentially return error if this is the only grade requested
            else:
                 return https_fn.Response(json.dumps({"status":"error", "message":f"Grade with ID {grade_id_param} not found."}),
                                       status=404, mimetype="application/json", headers=CORS_HEADERS)
        elif comp_id_param: # Process all grades for a specific competition
            logger.info(f"Fetching grades for Competition ID: {comp_id_param}")
            query = grades_collection.where("comp_id", "==", str(comp_id_param)) # Assuming comp_id is stored as string
            if limit_grades_param and limit_grades_param > 0: query = query.limit(limit_grades_param)
            for grade_doc in query.stream():
                 grades_to_process.append({"id": grade_doc.id, **grade_doc.to_dict()})
        else: # Process all active grades (default behavior if no specific IDs given)
            logger.info(f"Fetching all active grades. Limit: {limit_grades_param}")
            query = grades_collection.where("active", "==", True)
            if limit_grades_param and limit_grades_param > 0: query = query.limit(limit_grades_param)
            for grade_doc in query.stream():
                 grades_to_process.append({"id": grade_doc.id, **grade_doc.to_dict()})
        
        if not grades_to_process:
            return https_fn.Response(json.dumps({"status":"success", "message":"No grades found to process based on parameters."}),
                                   status=200, mimetype="application/json", headers=CORS_HEADERS)
        
        logger.info(f"Processing {len(grades_to_process)} grades. Dry run: {dry_run_param}")
        
        session = requests.Session()
        total_teams_found_all_grades = 0
        total_teams_saved_all_grades = 0
        total_mentone_teams_saved = 0
        grades_fully_processed_count = 0
        error_count = 0
        start_time_overall = time.time()

        for i, grade_data_from_db in enumerate(grades_to_process):
            grade_name_log = grade_data_from_db.get('name', grade_data_from_db.get('id', f'Unknown Grade {i+1}'))
            logger.info(f"Starting processing for grade {i+1}/{len(grades_to_process)}: {grade_name_log}")
            start_time_grade = time.time()
            try:
                teams_found_for_grade = discover_teams_for_grade_cf(grade_data_from_db, session)
                total_teams_found_all_grades += len(teams_found_for_grade)
                
                saved_count_this_grade = 0
                mentone_saved_this_grade = 0
                for team_obj in teams_found_for_grade:
                    if save_team_cf(db, team_obj, dry_run_param):
                        saved_count_this_grade += 1
                        if team_obj.get("is_home_club"):
                            mentone_saved_this_grade +=1
                    else:
                        error_count += 1 # Error during team save
                
                total_teams_saved_all_grades += saved_count_this_grade
                total_mentone_teams_saved += mentone_saved_this_grade
                grades_fully_processed_count += 1
                logger.info(f"Grade {grade_name_log} processed in {time.time() - start_time_grade:.2f}s. Found {len(teams_found_for_grade)} teams, saved {saved_count_this_grade} ({mentone_saved_this_grade} Mentone).")
            except Exception as e_grade_proc:
                logger.error(f"Error processing grade {grade_name_log}: {e_grade_proc}", exc_info=True)
                error_count += 1
            
            if i < len(grades_to_process) - 1: time.sleep(DELAY_BETWEEN_REQUESTS_CF)

        duration_overall = time.time() - start_time_overall
        summary_msg = (
            f"Team discovery finished in {duration_overall:.2f}s. "
            f"Grades processed: {grades_fully_processed_count}/{len(grades_to_process)}. "
            f"Total teams found: {total_teams_found_all_grades}. Teams saved/dry-run: {total_teams_saved_all_grades} "
            f"({total_mentone_teams_saved} Mentone). Errors: {error_count}."
        )
        logger.info(summary_msg)
        if dry_run_param: logger.info("DRY RUN active. No actual database writes occurred.")

        return https_fn.Response(
            json.dumps({
                "status": "success", "message": summary_msg,
                "data": {
                    "grades_queried": len(grades_to_process),
                    "grades_processed": grades_fully_processed_count,
                    "teams_found": total_teams_found_all_grades,
                    "teams_saved_or_dryrun": total_teams_saved_all_grades,
                    "mentone_teams_saved_or_dryrun": total_mentone_teams_saved,
                    "errors": error_count,
                    "duration_seconds": round(duration_overall, 2),
                    "dry_run": dry_run_param
                }
            }),
            status=200, mimetype="application/json", headers=CORS_HEADERS
        )

    except Exception as e_main_handler:
        logger.error(f"Critical error in discover_teams_cf main handler: {str(e_main_handler)}", exc_info=True)
        return https_fn.Response(
            json.dumps({"status": "error", "message": f"Critical error: {str(e_main_handler)}"}),
            status=500, mimetype="application/json", headers=CORS_HEADERS
        )
