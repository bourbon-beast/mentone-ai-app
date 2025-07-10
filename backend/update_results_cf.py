"""
Cloud Function to update Hockey Victoria game results in Firestore.
"""
import json
import re
import time
from datetime import datetime, timedelta

import firebase_admin
import requests
import pytz 
from bs4 import BeautifulSoup
from firebase_functions import https_fn
from firebase_admin import initialize_app, firestore # Ensure firestore is imported for SERVER_TIMESTAMP

# --- Global Variables & Constants ---
try:
    firebase_admin.get_app()
except ValueError:
    initialize_app()

BASE_URL = "https://www.hockeyvictoria.org.au" # Not strictly needed if URLs are in DB
GAME_URL_TEMPLATE = "https://www.hockeyvictoria.org.au/game/{game_id}" # Used if URL is missing
DELAY_BETWEEN_REQUESTS_CF = 0.25  # seconds
AUSTRALIA_TZ = pytz.timezone("Australia/Melbourne")
DEFAULT_DAYS_BACK_CF = 7
TEAM_FILTER_KEYWORD = "Mentone" # Used to determine mentone_result

# --- CORS Headers ---
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
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
        # Add a user-agent to mimic a browser, reducing chances of being blocked.
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requester.get(url, timeout=timeout, headers=headers)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for {url}: {e}")
        return None

def clean_text_cf(text):
    if text is None: return ""
    return text.strip().replace('\n', ' ').replace('\r', ' ')

# --- Core Logic Functions (from update_results.py, adapted for CF) ---

def extract_game_result_from_page_cf(soup, game_firestore_id, game_doc_data_from_db):
    """
    Extracts game result details from a parsed game page.
    game_doc_data_from_db is used to check existing team names for mentone_result.
    """
    update_payload = {}
    home_score_val, away_score_val = None, None
    status_changed_in_scrape = False

    # 1. Primary Score Extraction (from <h1 class="h2 mb-0">)
    score_h1_tag = soup.select_one("h1.h2.mb-0")
    if score_h1_tag:
        score_text_h1 = score_h1_tag.get_text(separator="-", strip=True)
        scores_h1 = [s.strip() for s in score_text_h1.split('-')]
        if len(scores_h1) == 2:
            try:
                home_score_val = int(scores_h1[0])
                away_score_val = int(scores_h1[1])
                logger.debug(f"Game {game_firestore_id}: Scores from h1: Home={home_score_val}, Away={away_score_val}")
                update_payload["status"] = "completed"
                status_changed_in_scrape = True
            except ValueError:
                logger.warning(f"Game {game_firestore_id}: Non-numeric scores in h1: '{score_text_h1}'. Storing raw.")
                # Using dot notation for Firestore field updates if sub-documents are structured this way
                update_payload["home_team.score_raw"] = scores_h1[0]
                update_payload["away_team.score_raw"] = scores_h1[1]
                update_payload["status"] = "completed" # Still assume completed
                status_changed_in_scrape = True
        else:
            logger.warning(f"Game {game_firestore_id}: Unexpected score format in h1: '{score_text_h1}'")
    else: # Fallback: try to find score in other common locations if primary fails
        # Example: Look for divs with specific score patterns if HV changes layout
        # score_div_fallback = soup.find(...)
        # if score_div_fallback: ...
        pass


    # 2. Winner Text Extraction
    winner_h2_tag = soup.select_one('h2.h4') # Often "Team X win!" or "Teams drew!"
    if winner_h2_tag:
        winner_text = clean_text_cf(winner_h2_tag.text)
        if winner_text:
            update_payload["winner_text"] = winner_text
            logger.debug(f"Game {game_firestore_id}: Winner text: '{winner_text}'")
            if not status_changed_in_scrape and update_payload.get("status") != "completed":
                update_payload["status"] = "completed"
                status_changed_in_scrape = True
    
    # 3. Forfeit/Cancelled/Postponed Check (only if scores not found and status not yet completed)
    if home_score_val is None and not status_changed_in_scrape:
        page_text_lower = soup.get_text().lower()
        special_status_terms = ["forfeit", "cancelled", "postponed", "abandoned", "washed out"]
        for term in special_status_terms:
            if term in page_text_lower:
                logger.info(f"Game {game_firestore_id}: Detected special status term '{term}'.")
                update_payload["status"] = term
                status_changed_in_scrape = True
                # For forfeits, scores might remain None or be set to a standard (e.g., 0-0 or specific forfeit score)
                # This depends on application logic for displaying forfeits.
                break # First detected term wins

    # Finalize payload based on findings
    if status_changed_in_scrape:
        if update_payload.get("status") == "completed": # Includes cases where scores were found or winner text implied completion
            # Only add numeric scores if raw scores were not already set
            if "home_team.score_raw" not in update_payload:
                update_payload["home_team.score"] = home_score_val
            if "away_team.score_raw" not in update_payload:
                update_payload["away_team.score"] = away_score_val

            # Determine Mentone result if numeric scores are available
            if home_score_val is not None and away_score_val is not None:
                home_team_name = game_doc_data_from_db.get("home_team", {}).get("name", "").lower()
                away_team_name = game_doc_data_from_db.get("away_team", {}).get("name", "").lower()
                
                if TEAM_FILTER_KEYWORD.lower() in home_team_name:
                    if home_score_val > away_score_val: update_payload["mentone_result"] = "win"
                    elif home_score_val < away_score_val: update_payload["mentone_result"] = "loss"
                    else: update_payload["mentone_result"] = "draw"
                elif TEAM_FILTER_KEYWORD.lower() in away_team_name:
                    if away_score_val > home_score_val: update_payload["mentone_result"] = "win"
                    elif away_score_val < home_score_val: update_payload["mentone_result"] = "loss"
                    else: update_payload["mentone_result"] = "draw"
            
            logger.info(f"Game {game_firestore_id}: Result update - Status: {update_payload.get('status')}, Home: {home_score_val}, Away: {away_score_val}, Mentone: {update_payload.get('mentone_result')}")
        
        elif update_payload.get("status") in special_status_terms: # e.g. postponed, cancelled
             logger.info(f"Game {game_firestore_id}: Status update - {update_payload['status']}")
        
        return update_payload # Return all fields identified for update
    
    logger.debug(f"Game {game_firestore_id}: No conclusive result or status change found.")
    return None # No updates to make based on scrape


def update_game_in_firestore_cf(db_client, game_firestore_id, result_payload, dry_run_mode):
    """Updates a game document in Firestore with the extracted result payload."""
    if not result_payload:
        logger.debug(f"Game {game_firestore_id}: No result payload to update.")
        return False, "no_payload"

    game_ref = db_client.collection("games").document(game_firestore_id)
    # Add common metadata to every update attempt that has a payload
    result_payload["results_retrieved_at"] = firestore.SERVER_TIMESTAMP 
    result_payload["results_script_version"] = "cf-1.0" # Version your CF logic

    if dry_run_mode:
        logger.info(f"[DRY RUN] Game {game_firestore_id}: Would update with: {result_payload}")
        return True, "dry_run"
    try:
        # Note: Using dict dot notation for subfields e.g. "home_team.score" requires those fields to be part of a map in Firestore.
        # If "home_team" is a map, game_ref.update({"home_team.score": X}) works.
        # If you want to replace the entire home_team map, structure payload like: {"home_team": {"score": X, ...}}
        # The current payload structure from extract_game_result_from_page_cf seems to use dot notation.
        game_ref.update(result_payload) # SERVER_TIMESTAMP for updated_at is good practice
        logger.info(f"Game {game_firestore_id}: Firestore updated successfully.")
        return True, "updated"
    except Exception as e_save:
        logger.error(f"Game {game_firestore_id}: Failed to update Firestore: {e_save}", exc_info=True)
        return False, "error"

# --- Cloud Function Entry Point ---
@https_fn.on_request()
def update_results_cf(req: https_fn.Request) -> https_fn.Response:
    if req.method == 'OPTIONS':
        return https_fn.Response("", status=204, headers=CORS_HEADERS)

    log_level_param = req.args.get("log_level", "INFO").upper()
    logger.setLevel(getattr(logging, log_level_param, logging.INFO))
    logger.info(f"update_results_cf triggered. Log level: {log_level_param}")

    db = firestore.client()
    session = requests.Session()

    # Request Parameters
    game_id_param = req.args.get("game_id") # Firestore game document ID
    days_back_param = int(req.args.get("days_back", str(DEFAULT_DAYS_BACK_CF)))
    limit_games_param = int(req.args.get("limit_games", "10")) # Default limit for safety
    dry_run_param = req.args.get("dry_run", "false").lower() == "true"
    force_update_param = req.args.get("force_update", "false").lower() == "true" # Re-process even if 'completed'

    games_to_check = []
    try:
        if game_id_param:
            logger.info(f"Fetching specific game by Firestore ID: {game_id_param}")
            game_doc = db.collection("games").document(game_id_param).get()
            if game_doc.exists:
                g_data = game_doc.to_dict(); g_data["id"] = game_doc.id
                games_to_check.append(g_data)
            else:
                return https_fn.Response(json.dumps({"status":"error", "message":f"Game with ID {game_id_param} not found."}),
                                       status=404, mimetype="application/json", headers=CORS_HEADERS)
        else:
            logger.info(f"Querying games from {days_back_param} days ago, limit {limit_games_param}. Force update: {force_update_param}")
            query_time_utc = datetime.now(pytz.utc)
            start_date_boundary = query_time_utc - timedelta(days=days_back_param)
            
            games_query = db.collection("games").where("mentone_playing", "==", True) \
                                             .where("date", ">=", start_date_boundary) \
                                             .where("date", "<=", query_time_utc) # Ensure game date is in the past or present
            
            if not force_update_param: # Common case: only process non-completed games
                 games_query = games_query.where("status", "in", ["scheduled", "unknown_outcome", "postponed"]) # Add other re-checkable statuses
            
            games_query = games_query.order_by("date", direction=firestore.Query.DESCENDING).limit(limit_games_param)

            for doc in games_query.stream():
                g_data = doc.to_dict(); g_data["id"] = doc.id
                games_to_check.append(g_data)
        
        if not games_to_check:
            return https_fn.Response(json.dumps({"status":"success", "message":"No games found to check based on parameters."}),
                                   status=200, mimetype="application/json", headers=CORS_HEADERS)
        
        logger.info(f"Found {len(games_to_check)} games to check for results. Dry run: {dry_run_param}")
        
        games_updated_in_run = 0
        games_processed_count = 0
        errors_in_run = 0
        start_time_overall = time.time()

        for i, game_data_from_db in enumerate(games_to_check):
            game_fs_id = game_data_from_db["id"] # Firestore Document ID
            game_hv_url = game_data_from_db.get("url")
            if not game_hv_url: # Construct HV game URL if missing in DB
                 # Assume 'id' or a specific 'hv_game_id' field holds the numeric ID for HV
                 hv_numeric_id = game_data_from_db.get("hv_game_id", game_fs_id) 
                 game_hv_url = GAME_URL_TEMPLATE.format(game_id=str(hv_numeric_id))

            logger.info(f"Processing game {i+1}/{len(games_to_check)}: ID {game_fs_id}, URL {game_hv_url}")
            
            response = make_request_cf(game_hv_url, session=session)
            if not response:
                errors_in_run += 1
                continue # Skip to next game if page fetch fails
            
            soup = BeautifulSoup(response.text, 'html.parser')
            result_payload_for_update = extract_game_result_from_page_cf(soup, game_fs_id, game_data_from_db)
            games_processed_count +=1

            if result_payload_for_update:
                success, status_msg = update_game_in_firestore_cf(db, game_fs_id, result_payload_for_update, dry_run_param)
                if success and status_msg != "error": games_updated_in_run += 1
                if status_msg == "error": errors_in_run += 1
            else: # No update identified from scrape
                logger.debug(f"Game {game_fs_id}: No updates identified from scrape.")

            if i < len(games_to_check) - 1: time.sleep(DELAY_BETWEEN_REQUESTS_CF)

        duration_overall = time.time() - start_time_overall
        summary_msg = (
            f"Game results update finished in {duration_overall:.2f}s. "
            f"Games checked: {games_processed_count}/{len(games_to_check)}. "
            f"Games updated in Firestore: {games_updated_in_run}. "
            f"Errors: {errors_in_run}."
        )
        logger.info(summary_msg)
        if dry_run_param: logger.info("DRY RUN active. No actual database writes occurred.")

        return https_fn.Response(
            json.dumps({
                "status": "success", "message": summary_msg,
                "data": {
                    "games_queried": len(games_to_check),
                    "games_processed_for_results": games_processed_count,
                    "games_updated_in_firestore": games_updated_in_run,
                    "errors": errors_in_run,
                    "duration_seconds": round(duration_overall, 2),
                    "dry_run": dry_run_param
                }
            }),
            status=200, mimetype="application/json", headers=CORS_HEADERS
        )

    except Exception as e_main_handler:
        logger.error(f"Critical error in update_results_cf main handler: {str(e_main_handler)}", exc_info=True)
        return https_fn.Response(
            json.dumps({"status": "error", "message": f"Critical error: {str(e_main_handler)}"}),
            status=500, mimetype="application/json", headers=CORS_HEADERS
        )
