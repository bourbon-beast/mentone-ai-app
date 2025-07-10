"""
Cloud Function to discover Hockey Victoria games for teams.
"""
import json
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin

import firebase_admin
import requests
import pytz # For timezone handling
from bs4 import BeautifulSoup
from firebase_functions import https_fn
from firebase_admin import initialize_app, firestore
# from google.cloud.firestore_v1.document import DocumentReference # Not strictly needed if using string paths for refs

# --- Global Variables & Constants ---
try:
    firebase_admin.get_app()
except ValueError:
    initialize_app()

# Constants from the original script
BASE_URL = "https://www.hockeyvictoria.org.au"
DRAW_URL_TEMPLATE = "https://www.hockeyvictoria.org.au/games/{comp_id}/{fixture_id}"
DEFAULT_DAYS_AHEAD = 30 # Not directly used in CF logic, but kept for reference
MAX_ROUNDS_TO_CHECK = 23 # Default max rounds if not specified in request
AUSTRALIA_TZ = pytz.timezone("Australia/Melbourne")


# --- CORS Headers ---
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",  # Adjust for production
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

# --- Logging Setup (Simplified) ---
import logging
logger = logging.getLogger(__name__)
# Initial level, can be changed by request param
logger.setLevel(logging.INFO)


# --- Utility Functions (Adapted or Inlined) ---
def make_request(url, session=None, timeout=15):
    requester = session if session else requests.Session()
    try:
        response = requester.get(url, timeout=timeout)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for {url}: {e}")
        return None

def clean_text(text):
    if text is None:
        return ""
    return text.strip().replace('\n', ' ').replace('\r', '')

def is_mentone_team(team_name):
    """Checks if the team name indicates it's a Mentone team."""
    if not team_name:
        return False
    return "mentone" in team_name.lower()

def parse_date_hv(date_string_raw, formats=None, timezone=AUSTRALIA_TZ):
    """
    Parses a date string which might include day, date, month, year, and time.
    Expected format examples: "Sat 06 Apr 2024 14:00", "Wed 10 Apr 2024 18:30"
    """
    if not date_string_raw:
        return None
    pattern = r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})\s+(\d{1,2}:\d{2})'
    match = re.search(pattern, date_string_raw)
    if not match:
        logger.debug(f"Could not extract standard date pattern from: '{date_string_raw}'")
        return None
    
    day, d, month_str, year, time_str = match.groups()
    clean_date_string = f"{day} {d} {month_str} {year} {time_str}"
    
    if formats is None:
        formats = ["%a %d %b %Y %H:%M"] # Hockey Vic format

    dt_obj = None
    for fmt in formats:
        try:
            dt_obj = datetime.strptime(clean_date_string, fmt)
            break
        except ValueError:
            continue
    
    if dt_obj and timezone:
        return timezone.localize(dt_obj)
    elif dt_obj:
        return dt_obj
    
    logger.warning(f"Failed to parse cleaned date string '{clean_date_string}' with formats: {formats}")
    return None


# --- Core Logic Functions (from discover_games.py, adapted for CF) ---

def discover_games_for_team_cf(team_data, session_obj, max_rounds_val):
    """
    Discovers games for a single team.
    team_data: dict containing team info (id, name, comp_id, fixture_id, is_home_club)
    session_obj: requests.Session object
    max_rounds_val: int, max number of rounds to check
    """
    comp_id = team_data.get("comp_id")
    fixture_id = team_data.get("fixture_id")
    team_name = team_data.get("name", team_data.get("id", "Unknown Team"))

    if not comp_id or not fixture_id:
        logger.error(f"Missing comp_id or fixture_id for team: {team_name}")
        return []

    base_draw_url = DRAW_URL_TEMPLATE.format(comp_id=comp_id, fixture_id=fixture_id)
    logger.info(f"Discovering games for team: {team_name} (Comp: {comp_id}, Fix: {fixture_id}), Base: {base_draw_url}, Max Rounds: {max_rounds_val}")

    all_games_list = []
    round_num = 1
    empty_rounds_consecutive = 0

    while round_num <= max_rounds_val:
        round_url = f"{base_draw_url}/round/{round_num}"
        logger.debug(f"Team {team_name}: Checking round {round_num} at {round_url}")
        response = make_request(round_url, session=session_obj)

        if not response or response.status_code != 200:
            logger.info(f"Team {team_name}: No more rounds data or error for round {round_num}. Status: {response.status_code if response else 'No response'}")
            break 

        soup = BeautifulSoup(response.text, "html.parser")
        game_cards = soup.select("div.card-body")

        if not game_cards:
            logger.info(f"Team {team_name}: No game cards found for round {round_num}")
            empty_rounds_consecutive += 1
            if empty_rounds_consecutive >= 3: # Stop if 3 consecutive rounds have no games
                logger.info(f"Team {team_name}: Stopping after {empty_rounds_consecutive} consecutive empty rounds.")
                break
            round_num += 1
            time.sleep(0.2) # Small delay before next round
            continue
        
        empty_rounds_consecutive = 0 # Reset counter if cards are found

        for card_idx, card in enumerate(game_cards):
            try:
                # Initialize game details for each card
                game_date, venue, home_team_name, away_team_name = None, "TBD", "", ""
                home_team_id, away_team_id, game_id, game_url = None, None, None, None
                home_score, away_score, status, venue_code = None, None, "scheduled", ""

                date_time_div = card.select_one("div.col-md.pb-3.pb-lg-0.text-center.text-md-left")
                if not date_time_div: 
                    logger.debug(f"Team {team_name}, Round {round_num}, Card {card_idx}: No date/time div.")
                    continue
                
                date_time_html = str(date_time_div).replace('<br>', ' ').replace('<br/>', ' ')
                date_time_text = clean_text(BeautifulSoup(date_time_html, 'html.parser').get_text())
                game_date = parse_date_hv(date_time_text)
                if not game_date:
                    logger.warning(f"Team {team_name}, R{round_num}, C{card_idx}: Failed date parse: '{date_time_text}'")
                    continue

                venue_div = card.select_one("div.col-md.pb-3.pb-lg-0.text-center.text-md-right.text-lg-left")
                if venue_div:
                    venue_link = venue_div.select_one("a")
                    if venue_link: venue = clean_text(venue_link.text)
                    venue_code_elem = venue_div.select_one("div")
                    if venue_code_elem: venue_code = clean_text(venue_code_elem.text)

                teams_div = card.select_one("div.col-lg-3.pb-3.pb-lg-0.text-center")
                if not teams_div: 
                    logger.debug(f"Team {team_name}, R{round_num}, C{card_idx}: No teams div.")
                    continue
                team_links = teams_div.select("a")
                if len(team_links) < 2: 
                    logger.debug(f"Team {team_name}, R{round_num}, C{card_idx}: Not enough team links.")
                    continue

                home_team_name = clean_text(team_links[0].text)
                away_team_name = clean_text(team_links[1].text)
                
                home_is_mentone = is_mentone_team(home_team_name)
                away_is_mentone = is_mentone_team(away_team_name)
                
                if team_data.get("is_home_club", False) and not (home_is_mentone or away_is_mentone):
                    logger.debug(f"Team {team_name}, R{round_num}, C{card_idx}: Skipping non-Mentone game for Mentone team.")
                    continue # Skip if this is a Mentone team but Mentone is not playing

                home_team_id_match = re.search(r'/team/(\d+)', team_links[0].get("href", ""))
                if home_team_id_match: home_team_id = home_team_id_match.group(1)
                
                away_team_id_match = re.search(r'/team/(\d+)', team_links[1].get("href", ""))
                if away_team_id_match: away_team_id = away_team_id_match.group(1)

                score_div = teams_div.select_one("div b") # Score usually in bold
                if score_div:
                    score_text = clean_text(score_div.text)
                    score_parts = score_text.split('-')
                    if len(score_parts) == 2:
                        try:
                            home_score = int(score_parts[0].strip())
                            away_score = int(score_parts[1].strip())
                            status = "completed"
                        except ValueError:
                            logger.warning(f"Team {team_name}, R{round_num}, C{card_idx}: Could not parse score: '{score_text}'")
                
                details_link_elem = card.select_one("a.btn.btn-outline-primary.btn-sm") # Link to game details page
                if details_link_elem:
                    game_path = details_link_elem.get("href", "")
                    game_url = urljoin(BASE_URL, game_path)
                    game_id_match = re.search(r'/game/(\d+)', game_path)
                    if game_id_match: game_id = game_id_match.group(1)

                if not game_id: # Fallback game ID
                    unique_str = f"{comp_id}_{fixture_id}_{game_date.strftime('%Y%m%d%H%M')}_{home_team_name}_{away_team_name}"
                    game_id = str(abs(hash(unique_str)) % (10 ** 10)) # Create a somewhat unique ID

                game_entry = {
                    "id": str(game_id), "comp_id": str(comp_id), "fixture_id": str(fixture_id),
                    "team_id": str(team_data.get("id")), # ID of the team this game was discovered for
                    "date": game_date, "venue": venue, "venue_code": venue_code,
                    "round": round_num, "status": status, "url": game_url,
                    "mentone_playing": home_is_mentone or away_is_mentone,
                    "type": team_data.get("type"), 
                    "updated_at": datetime.now(pytz.utc), 
                    "created_at": datetime.now(pytz.utc), 
                    "home_team": {"id": str(home_team_id) if home_team_id else None, "name": home_team_name, "score": home_score, "is_mentone": home_is_mentone},
                    "away_team": {"id": str(away_team_id) if away_team_id else None, "name": away_team_name, "score": away_score, "is_mentone": away_is_mentone},
                }
                all_games_list.append(game_entry)
            except Exception as e_card:
                logger.error(f"Team {team_name}, R{round_num}, C{card_idx}: Error processing game card: {e_card}", exc_info=True)
                continue # next card
        
        round_num += 1
        time.sleep(0.1) # Shorter delay between rounds for CF

    logger.info(f"Team {team_name}: Discovered {len(all_games_list)} games across {round_num-1} rounds.")
    return all_games_list


def create_or_update_game_cf(db, game_details, dry_run_mode=False):
    """Saves a game to Firestore. Returns (bool: success, str: status_message)"""
    if dry_run_mode:
        logger.info(f"[DRY RUN] Would save game: {game_details.get('id')} for round {game_details.get('round')}")
        return True, "dry_run"

    game_id = str(game_details["id"]) # Ensure ID is a string
    game_ref = db.collection("games").document(game_id)

    try:
        # Convert datetimes to UTC for Firestore, ensure they are timezone-aware first
        if isinstance(game_details.get("date"), datetime):
            dt = game_details["date"]
            if dt.tzinfo is None: # Should be localized by parse_date_hv already
                game_details["date"] = AUSTRALIA_TZ.localize(dt).astimezone(pytz.utc)
            else:
                game_details["date"] = dt.astimezone(pytz.utc)
        
        current_time_utc = datetime.now(pytz.utc)
        game_details["updated_at"] = current_time_utc
        
        existing_doc = game_ref.get()
        if existing_doc.exists:
            game_details["created_at"] = existing_doc.to_dict().get("created_at", current_time_utc)
        else:
            game_details["created_at"] = current_time_utc
        
        # Store references as string paths
        game_details["competition_ref_str"] = f"competitions/{game_details['comp_id']}"
        game_details["grade_ref_str"] = f"grades/{game_details['fixture_id']}"
        if game_details["home_team"].get("id"):
             game_details["home_team_ref_str"] = f"teams/{game_details['home_team']['id']}"
        if game_details["away_team"].get("id"):
            game_details["away_team_ref_str"] = f"teams/{game_details['away_team']['id']}"

        game_ref.set(game_details, merge=True)
        logger.debug(f"Game {game_id} (Round {game_details.get('round')}) saved successfully.")
        return True, "saved"
    except Exception as e_save:
        logger.error(f"Failed to save game {game_id}: {str(e_save)}", exc_info=True)
        return False, "error"


# --- Cloud Function Entry Point ---
@https_fn.on_request()
def discover_games_cf(req: https_fn.Request) -> https_fn.Response:
    if req.method == 'OPTIONS': # Handle CORS preflight
        return https_fn.Response("", status=204, headers=CORS_HEADERS)

    log_level_param = req.args.get("log_level", "INFO").upper()
    logger.setLevel(getattr(logging, log_level_param, logging.INFO))
    logger.info(f"discover_games_cf triggered. Log level: {log_level_param}")
    
    db = firestore.client()
    
    # Get request parameters
    team_id_param = req.args.get("team_id") # Process specific team
    max_rounds_param = int(req.args.get("max_rounds", str(MAX_ROUNDS_TO_CHECK)))
    dry_run_param = req.args.get("dry_run", "false").lower() == "true"
    mentone_teams_only_param = req.args.get("mentone_only", "true").lower() == "true" # Default to Mentone teams
    limit_teams_param = req.args.get("limit_teams", type=int) # Optional: limit number of teams processed

    teams_to_process = []
    try:
        teams_collection_ref = db.collection("teams")
        if team_id_param:
            logger.info(f"Fetching specific team by ID: {team_id_param}")
            team_doc = teams_collection_ref.document(team_id_param).get()
            if team_doc.exists:
                teams_to_process.append({"id": team_doc.id, **team_doc.to_dict()})
            else:
                return https_fn.Response(json.dumps({"status": "error", "message": f"Team {team_id_param} not found"}),
                                       status=404, mimetype="application/json", headers=CORS_HEADERS)
        else:
            logger.info(f"Fetching teams. Mentone only: {mentone_teams_only_param}. Limit: {limit_teams_param}")
            query = teams_collection_ref
            if mentone_teams_only_param:
                 query = query.where("is_home_club", "==", True) # From original script logic
            
            if limit_teams_param and limit_teams_param > 0:
                query = query.limit(limit_teams_param)

            for team_doc in query.stream():
                teams_to_process.append({"id": team_doc.id, **team_doc.to_dict()})
        
        if not teams_to_process:
            return https_fn.Response(json.dumps({"status": "success", "message": "No teams found to process"}),
                                   status=200, mimetype="application/json", headers=CORS_HEADERS)

        logger.info(f"Processing {len(teams_to_process)} teams. Max rounds per team: {max_rounds_param}. Dry run: {dry_run_param}")
        
        session = requests.Session() # Use a session for all requests
        total_games_found_all_teams = 0
        total_games_saved_all_teams = 0
        teams_processed_count = 0
        error_count = 0
        start_time_overall = time.time()

        for i, team_data in enumerate(teams_to_process):
            team_name_log = team_data.get('name', team_data.get('id', f'Unknown Team {i+1}'))
            logger.info(f"Starting processing for team {i+1}/{len(teams_to_process)}: {team_name_log}")
            start_time_team = time.time()
            try:
                games_for_single_team = discover_games_for_team_cf(team_data, session, max_rounds_param)
                total_games_found_all_teams += len(games_for_single_team)
                
                saved_count_this_team = 0
                for game in games_for_single_team:
                    success, status_msg = create_or_update_game_cf(db, game, dry_run_param)
                    if success and status_msg != "error": # "dry_run" is also a success
                        saved_count_this_team +=1
                    if status_msg == "error":
                        error_count +=1
                total_games_saved_all_teams += saved_count_this_team
                
                logger.info(f"Team {team_name_log}: {len(games_for_single_team)} games found, {saved_count_this_team} saved/dry-run. Time: {time.time() - start_time_team:.2f}s")
                teams_processed_count += 1
            except Exception as e_team_processing:
                logger.error(f"Error during processing of team {team_name_log}: {e_team_processing}", exc_info=True)
                error_count +=1
                # Optionally decide if to continue with other teams or break
            
            if i < len(teams_to_process) - 1: # If not the last team
                time.sleep(0.1) # Small polite delay between processing different teams

        duration_overall = time.time() - start_time_overall
        summary_message = (
            f"Game discovery finished in {duration_overall:.2f}s. "
            f"Teams processed: {teams_processed_count}/{len(teams_to_process)}. "
            f"Games found: {total_games_found_all_teams}. Games saved/dry-run: {total_games_saved_all_teams}. "
            f"Errors encountered: {error_count}."
        )
        logger.info(summary_message)
        if dry_run_param: logger.info("DRY RUN active - no actual database writes occurred for 'saved' games.")

        return https_fn.Response(
            json.dumps({
                "status": "success", "message": summary_message,
                "data": {
                    "teams_queried": len(teams_to_process),
                    "teams_processed": teams_processed_count,
                    "games_found": total_games_found_all_teams,
                    "games_saved_or_dryrun": total_games_saved_all_teams,
                    "errors": error_count,
                    "duration_seconds": round(duration_overall, 2),
                    "dry_run": dry_run_param,
                    "max_rounds_per_team": max_rounds_param
                }
            }),
            status=200, mimetype="application/json", headers=CORS_HEADERS
        )

    except Exception as e_main: # Catch-all for broader errors during setup or team fetching
        logger.error(f"Critical error in discover_games_cf main handler: {str(e_main)}", exc_info=True)
        return https_fn.Response(
            json.dumps({"status": "error", "message": f"Critical error: {str(e_main)}"}),
            status=500, mimetype="application/json", headers=CORS_HEADERS
        )
