# fetch_round_games.py
#
# Purpose: Fetches game data for Mentone teams by scanning round pages
#          for grades identified as new or needing a re-check.
#          Ensures accurate home/away team capture and naive timestamps.
# Key functions:
#   - Uses logic from 'add_new_data...' to identify grades needing scan.
#   - For each selected grade, iterates through round pages.
#   - Parses game details from round pages (home/away teams, date, venue etc.).
#   - Creates/updates game documents in Firestore using game_id.

import firebase_admin
from firebase_admin import credentials, firestore
import requests
from bs4 import BeautifulSoup
import re
import logging
import time
from urllib.parse import urljoin
from datetime import datetime, timedelta, timezone # Keep timezone for threshold check
import os
import concurrent.futures

# --- Basic Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s [%(funcName)s] - %(message)s',
    handlers=[
        logging.FileHandler(f"fetch_round_games_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Constants ---
# Inherit constants from add_new_data script where applicable
BASE_URL = "https://www.revolutionise.com.au/vichockey/games/"
HV_BASE = "https://www.hockeyvictoria.org.au"
TEAM_FILTER_KEYWORD = "Mentone"
REQUEST_TIMEOUT = 15
MAX_RETRIES = 3
RETRY_DELAY = 3
SCRIPT_VERSION = "1.0-fetch-round-games"
GRADE_RECHECK_THRESHOLD_HOURS = 24 * 7
MAX_CONCURRENT_WORKERS_ROUNDS = 3 # Be gentler when scanning rounds
MAX_BATCH_SIZE = 400
MAX_ROUNDS_TO_CHECK = 25 # Stop checking rounds after this number if no games found recently

# --- Regex Patterns ---
COMP_FIXTURE_REGEX = re.compile(r"/games/(\d+)/(\d+)")
TEAM_ID_REGEX = re.compile(r"/games/team/(\d+)/(\d+)")
GAME_ID_REGEX = re.compile(r'/game/(\d+)$')
PARENT_COMP_ID_REGEX = re.compile(r'/(?:reports/games|team-stats)/(\d+)')

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

# --- Helper Functions (Keep make_request, classify_item) ---
def make_request(url, retry_count=0):
    """Make an HTTP request with retries and error handling."""
    try: logger.debug(f"Requesting: {url}"); response = requests.get(url, timeout=REQUEST_TIMEOUT, headers={'User-Agent': f'MentoneHockeyApp-FetchRoundGames/{SCRIPT_VERSION}'}); response.raise_for_status(); return response
    except requests.exceptions.RequestException as e:
        if retry_count < MAX_RETRIES: wait_time = RETRY_DELAY * (retry_count + 1); logger.warning(f"Request to {url} failed: {e}. Retrying ({retry_count+1}/{MAX_RETRIES}) in {wait_time}s..."); time.sleep(wait_time); return make_request(url, retry_count + 1)
        else: logger.error(f"Request to {url} failed after {MAX_RETRIES} attempts: {e}"); return None

def parse_datetime_string_naive(date_str, time_str):
    """Parses date/time strings into a NAIVE datetime object."""
    try: full_str = f"{date_str} {time_str}"; dt = datetime.strptime(full_str, "%a %d %b %Y %H:%M"); return dt
    except ValueError:
        try: dt = datetime.strptime(full_str, "%a %d %b %Y %I:%M %p"); return dt # Try AM/PM format
        except ValueError: logger.warning(f"Could not parse naive datetime: {full_str}"); return None

def extract_team_id_from_href(href):
    match = TEAM_ID_REGEX.search(href); return match.group(2) if match else None

# --- Functions needed from add_new_data_ladder_focused ---
# (These are needed to determine which grades to scan)
def scrape_competitions_and_grades():
    # ... (Copy this function EXACTLY from add_new_data_ladder_focused.py) ...
    # ... (Or import it if you structure your code into modules) ...
    logger.info(f"Scraping main games page: {BASE_URL}"); parent_competitions = []; response = make_request(BASE_URL)
    if not response: return parent_competitions
    soup = BeautifulSoup(response.text, "html.parser"); potential_comp_starts = soup.select("h2.h4, div.p-4.d-md-flex.align-items-center.justify-content-between")
    if not potential_comp_starts: logger.error("Could not find competition starting elements."); return []
    logger.info(f"Found {len(potential_comp_starts)} potential competition starting points.")
    for start_element in potential_comp_starts:
        heading_tag = start_element.select_one("h2.h4"); heading_text = heading_tag.text.strip() if heading_tag else start_element.text.strip()
        parent_comp_id = None; parent_link = start_element.select_one("a[href*='/reports/games/'], a[href*='/team-stats/']")
        if parent_link and parent_link['href']: id_match = PARENT_COMP_ID_REGEX.search(parent_link['href']); parent_comp_id = id_match.group(1) if id_match else None
        if not parent_comp_id: logger.warning(f"Could not determine parent_comp_id for '{heading_text}'. Inferring.")
        logger.debug(f"Processing Block: {heading_text} (Parent ID tentative: {parent_comp_id})")
        current_comp = {'heading': heading_text, 'parent_comp_id': parent_comp_id, 'grades': []}; processed_fixtures = set()
        current_element = start_element.find_next_sibling()
        while current_element:
            if current_element.name == 'div' and current_element.select_one("h2.h4"): break
            if current_element.name == 'div' and 'px-4' in current_element.get('class', []):
                link_tag = current_element.find('a'); href = link_tag['href'] if link_tag else None
                if href:
                    match = COMP_FIXTURE_REGEX.search(href)
                    if match:
                        comp_id_from_link, fixture_id = match.groups()
                        if current_comp['parent_comp_id'] is None: current_comp['parent_comp_id'] = comp_id_from_link; logger.info(f"Inferred Parent ID for '{heading_text}' as {comp_id_from_link}.")
                        elif current_comp['parent_comp_id'] != comp_id_from_link: logger.warning(f"Grade link comp_id {comp_id_from_link} differs from parent {current_comp['parent_comp_id']} for '{heading_text}'.")
                        if fixture_id not in processed_fixtures:
                            grade_info = {"name": link_tag.text.strip(), "comp_id": comp_id_from_link, "fixture_id": fixture_id, "url": urljoin(HV_BASE, href)}; current_comp['grades'].append(grade_info); processed_fixtures.add(fixture_id); logger.debug(f"  Found Grade Link: '{grade_info['name']}' (Fixture: {fixture_id})")
            current_element = current_element.find_next_sibling()
        if current_comp['parent_comp_id'] and current_comp['grades']: parent_competitions.append(current_comp)
        elif not current_comp['grades']: logger.warning(f"No grade links found under block: '{heading_text}'")
        elif not current_comp['parent_comp_id']: logger.error(f"Could not determine parent_comp_id for block: '{heading_text}'.")
    logger.info(f"Successfully processed {len(parent_competitions)} competition structures.")
    return parent_competitions

def create_or_update_competition(comp_structure):
    # ... (Copy this function EXACTLY from add_new_data_ladder_focused.py) ...
    parent_comp_id = comp_structure.get('parent_comp_id'); heading = comp_structure.get('heading', 'Unknown');
    if not parent_comp_id: logger.error(f"Cannot process competition '{heading}', no ID."); return None, False
    doc_id = str(parent_comp_id); comp_ref = db.collection("competitions").document(doc_id); comp_doc = comp_ref.get()
    year_match = re.search(r'\b(20\d{2})\b', heading); season = year_match.group(1) if year_match else str(datetime.now().year)
    comp_type, _ = classify_item(heading)
    data_payload = { "id": int(parent_comp_id), "name": heading, "season": season, "type": comp_type, "updated_at": firestore.SERVER_TIMESTAMP, "last_checked": firestore.SERVER_TIMESTAMP, "active": True }
    if not comp_doc.exists:
        logger.info(f"Creating PARENT Competition: {heading} (ID: {doc_id})"); data_payload["created_at"] = firestore.SERVER_TIMESTAMP
        first_fixture_id = comp_structure['grades'][0]['fixture_id'] if comp_structure['grades'] else None
        if first_fixture_id: data_payload["fixture_id"] = int(first_fixture_id)
        try: comp_ref.set(data_payload); return comp_ref, True
        except Exception as e: logger.error(f"Failed to create competition {doc_id}: {e}"); return None, False
    else:
        logger.debug(f"Updating existing PARENT Competition: {heading} (ID: {doc_id})")
        try: update_data = { "name": heading, "season": season, "type": comp_type, "active": True, "updated_at": firestore.SERVER_TIMESTAMP, "last_checked": firestore.SERVER_TIMESTAMP }; comp_ref.update(update_data); return comp_ref, False
        except Exception as e: logger.warning(f"Failed to update competition {doc_id}: {e}"); return comp_ref, False

def create_or_update_grade(grade_info, parent_comp_ref):
    """Creates or updates a GRADE. Returns ref, created_bool, data_dict."""
    # ... (Copy this function EXACTLY from add_new_data_ladder_focused.py) ...
    fixture_id_str = str(grade_info['fixture_id']); doc_id = fixture_id_str; grade_ref = db.collection("grades").document(doc_id); grade_doc = grade_ref.get()
    grade_name = grade_info['name']; grade_type, gender = classify_item(grade_name); year_match = re.search(r'\b(20\d{2})\b', grade_name); season = str(datetime.now().year)
    if year_match: season = year_match.group(1)
    elif parent_comp_ref:
        try: parent_data = parent_comp_ref.get().to_dict(); season = parent_data['season'] if parent_data and 'season' in parent_data else season
        except Exception as e: logger.warning(f"Could not get season from parent ref for grade {doc_id}: {e}")
    data_payload = { "id": int(fixture_id_str), "name": grade_name, "fixture_id": int(fixture_id_str), "comp_id": int(grade_info['comp_id']), "parent_comp_ref": parent_comp_ref, "url": grade_info['url'], "type": grade_type, "gender": gender, "season": season, "updated_at": firestore.SERVER_TIMESTAMP, "last_checked": firestore.SERVER_TIMESTAMP, "active": True }
    if not grade_doc.exists:
        logger.info(f"Creating GRADE: {grade_name} (ID: {doc_id})"); data_payload["created_at"] = firestore.SERVER_TIMESTAMP
        try: grade_ref.set(data_payload); return grade_ref, True, data_payload
        except Exception as e: logger.error(f"Failed to create grade {doc_id}: {e}"); return None, False, None
    else:
        logger.debug(f"Updating existing GRADE: {grade_name} (ID: {doc_id})"); existing_data = grade_doc.to_dict()
        try: update_data = { k: v for k, v in data_payload.items() if k not in ["id", "created_at"] }; grade_ref.update(update_data); return grade_ref, False, existing_data
        except Exception as e: logger.warning(f"Failed to update grade {doc_id}: {e}"); return grade_ref, False, existing_data


# --- Game Data Processing ---
def parse_round_game_card(game_card_soup, grade_info):
    """Parses a single game card div from a ROUND page."""
    game_data = {}
    try:
        # Game ID and URL from Details button
        details_link = game_card_soup.select_one("a.btn[href*='/game/']")
        if not details_link: return None # Cannot identify game without details link
        game_data['url'] = urljoin(HV_BASE, details_link['href'])
        game_id_match = GAME_ID_REGEX.search(game_data['url'])
        if not game_id_match: logger.warning(f"Could not extract game ID from URL: {game_data['url']}"); return None
        game_data['game_id'] = game_id_match.group(1)

        # Basic Info (Round, Date, Time, Venue)
        left_col = game_card_soup.select_one("div.col-md.pb-3.pb-lg-0.text-center.text-md-left")
        if left_col:
            lines = [line.strip() for line in left_col.get_text("\n", strip=True).split("\n") if line.strip()]
            game_data['round'] = int(lines[0].replace("Round ", "").strip()) if lines and lines[0].startswith("Round") else None
            date_str = lines[1] if len(lines) > 1 and re.match(r'\w{3}\s\d{1,2}\s\w{3}\s\d{4}', lines[1]) else None
            time_str = lines[2] if len(lines) > 2 else (lines[1] if len(lines) > 1 and ":" in lines[1] else None)
            if date_str and time_str: game_data['date'] = parse_datetime_string_naive(date_str, time_str) # Store NAIVE time

        venue_col = game_card_soup.select_one("div.col-md.pb-3.pb-lg-0.text-center.text-md-right.text-lg-left")
        if venue_col:
            venue_link = venue_col.select_one("a"); game_data['venue'] = venue_link.text.strip() if venue_link else None
            venue_code_div = venue_col.select_one("div"); game_data['venue_short'] = venue_code_div.text.strip() if venue_code_div else None

        # Center Column (Teams, Status)
        center_col = game_card_soup.select_one("div.col-lg-3.pb-3.pb-lg-0.text-center")
        if center_col:
            team_links = center_col.select("a[href*='/games/team/']")
            if len(team_links) == 2: # Expect exactly two team links for home/away
                game_data['home_team'] = {'name': team_links[0].text.strip(), 'id': extract_team_id_from_href(team_links[0]['href'])}
                game_data['away_team'] = {'name': team_links[1].text.strip(), 'id': extract_team_id_from_href(team_links[1]['href'])}
                # Determine if Mentone is playing
                game_data['mentone_playing'] = TEAM_FILTER_KEYWORD.lower() in game_data['home_team']['name'].lower() or \
                                               TEAM_FILTER_KEYWORD.lower() in game_data['away_team']['name'].lower()
            else: logger.warning(f"Game {game_data['game_id']}: Found {len(team_links)} team links, expected 2.")

            status_text_div = center_col.select_one("div.text-muted")
            game_data['status_scraped'] = status_text_div.text.strip().lower() if status_text_div else 'unknown'

        # Add Grade/Comp context
        game_data['fixture_id'] = int(grade_info['fixture_id'])
        game_data['comp_id'] = int(grade_info['comp_id'])
        game_data['grade_ref'] = db.collection("grades").document(str(grade_info['fixture_id']))
        # Parent comp ref needs to be passed or looked up
        parent_comp_ref = db.collection("competitions").document(str(grade_info['comp_id'])) # Assuming grade comp_id IS parent
        game_data['competition_ref'] = parent_comp_ref

        return game_data

    except Exception as e: logger.error(f"Error parsing round game card: {e}", exc_info=True); return None


def fetch_and_process_grade_rounds(grade_info, grade_ref, parent_comp_ref):
    """Iterates through rounds for a grade, parses games, returns list of game data."""
    fixture_id = grade_info['fixture_id']
    comp_id = grade_info['comp_id']
    grade_name = grade_info['name']
    logger.info(f"Fetching rounds for Grade: {grade_name} (Fixture: {fixture_id})")

    all_games_in_grade = []
    processed_game_ids = set()
    consecutive_empty_rounds = 0

    for round_num in range(1, MAX_ROUNDS_TO_CHECK + 1):
        round_url = f"{HV_BASE}/games/{comp_id}/{fixture_id}/round/{round_num}"
        logger.debug(f"Fetching {round_url}")
        response = make_request(round_url)
        if not response:
            logger.warning(f"Failed to fetch round {round_num} for grade {fixture_id}. Stopping round check for this grade.")
            break # Stop checking rounds if one fails

        soup = BeautifulSoup(response.text, "html.parser")
        game_cards = soup.select("div.card.card-hover.mb-4")

        if not game_cards:
            logger.info(f"No game cards found on round {round_num} for grade {fixture_id}.")
            consecutive_empty_rounds += 1
            if consecutive_empty_rounds >= 3: # Stop if 3 empty rounds in a row
                logger.info(f"Stopping round check for grade {fixture_id} after 3 consecutive empty rounds.")
                break
            time.sleep(0.2) # Small delay even for empty rounds
            continue # Go to next round
        else:
            consecutive_empty_rounds = 0 # Reset counter if games found

        logger.info(f"Found {len(game_cards)} game cards on round {round_num} for grade {fixture_id}.")
        round_games_found = 0
        for card in game_cards:
            game_data = parse_round_game_card(card, grade_info)
            if game_data and game_data['game_id'] not in processed_game_ids:
                all_games_in_grade.append(game_data)
                processed_game_ids.add(game_data['game_id'])
                round_games_found += 1

        logger.debug(f"Parsed {round_games_found} unique games from round {round_num}.")
        time.sleep(0.3) # Delay between fetching rounds

    logger.info(f"Finished fetching rounds for grade {fixture_id}. Found {len(all_games_in_grade)} unique games.")
    return all_games_in_grade

def create_update_games_in_batch(db_client, all_parsed_games):
    """Takes parsed game data from ROUND pages and creates/updates docs."""
    logger.info(f"Starting Firestore create/update for {len(all_parsed_games)} parsed games...")
    games_ref = db_client.collection("games")
    batch = db_client.batch()
    batch_count = 0; created_count = 0; updated_count = 0; error_count = 0

    game_ids_to_check = list(all_parsed_games.keys()) # Games are now dict keyed by game_id
    existing_games_data = {}
    # Efficiently fetch existing games in chunks using 'in' query (max 10 per query)
    for i in range(0, len(game_ids_to_check), 10):
        chunk_ids = game_ids_to_check[i:i+10]
        try:
            docs = games_ref.where(firestore.FieldPath.document_id(), 'in', chunk_ids).stream()
            for doc in docs: existing_games_data[doc.id] = doc.to_dict()
        except Exception as e:
            logger.error(f"Error pre-fetching game chunk {chunk_ids}: {e}. Updates might overwrite results.")


    for game_id, game_data in all_parsed_games.items():
        try:
            game_ref = games_ref.document(game_id)
            existing_data = existing_games_data.get(game_id)

            # --- Prepare Firestore Payload ---
            home_team_id = game_data.get('home_team', {}).get('id')
            away_team_id = game_data.get('away_team', {}).get('id')

            payload = {
                "id": int(game_id) if game_id.isdigit() else game_id,
                "url": game_data.get('url'),
                "round": game_data.get('round'),
                "date": game_data.get('date'), # Should be NAIVE datetime
                "venue": game_data.get('venue'),
                "venue_short": game_data.get('venue_short'),
                "comp_id": game_data.get('comp_id'),
                "fixture_id": game_data.get('fixture_id'),
                "competition_ref": game_data.get('competition_ref'),
                "grade_ref": game_data.get('grade_ref'),
                "mentone_playing": game_data.get('mentone_playing', False),
                "updated_at": firestore.SERVER_TIMESTAMP,
                "last_scraped_from_round_page": firestore.SERVER_TIMESTAMP, # New field
                # --- Home/Away Team Structure ---
                "home_team": {
                    "id": home_team_id, # String team ID
                    "name": game_data.get('home_team', {}).get('name'),
                    "score": None, # Initialize score, results script updates
                    "club": None, # Add club info if needed later
                    "club_id": None
                },
                "away_team": {
                    "id": away_team_id, # String team ID
                    "name": game_data.get('away_team', {}).get('name'),
                    "score": None, # Initialize score
                    "club": None,
                    "club_id": None
                },
                # Team Refs Array
                "team_refs": []
            }
            if home_team_id: payload['team_refs'].append(db.collection("teams").document(str(home_team_id)))
            if away_team_id: payload['team_refs'].append(db.collection("teams").document(str(away_team_id)))


            # --- Handle Create vs Update ---
            if not existing_data:
                logger.info(f"Creating game {game_id} (Round {payload['round']})")
                payload["created_at"] = firestore.SERVER_TIMESTAMP
                # Set initial status based on what was scraped from round page
                scraped_status = game_data.get('status_scraped')
                if scraped_status == "played" or scraped_status == "completed": payload["status"] = "completed" # If round page says played, mark completed
                else: payload["status"] = "scheduled" # Default to scheduled
                payload.pop('status_scraped', None) # Remove temporary field

                batch.set(game_ref, payload)
                created_count += 1
            else:
                logger.debug(f"Updating game {game_id} (Round {payload['round']})")
                update_data = payload.copy()
                # Remove fields results_update.py should manage exclusively
                update_data.pop('created_at', None); update_data.pop('id', None)
                update_data.pop('status', None) # Don't overwrite status unless logic dictates
                update_data.pop('winner_text', None); update_data.pop('results_retrieved_at', None)
                # Don't overwrite scores from this script
                update_data['home_team'].pop('score', None)
                update_data['away_team'].pop('score', None)
                # Merge potentially missing sub-fields carefully if needed (e.g., if results added club_id)
                if existing_data.get('home_team'): update_data['home_team'] = {**existing_data['home_team'], **update_data['home_team']}
                if existing_data.get('away_team'): update_data['away_team'] = {**existing_data['away_team'], **update_data['away_team']}

                # Update status only if currently scheduled and round page says played
                current_status = existing_data.get('status', 'unknown')
                scraped_status = game_data.get('status_scraped')
                if current_status == 'scheduled' and (scraped_status == "played" or scraped_status == "completed"):
                    update_data['status'] = 'completed'
                    logger.info(f"Game {game_id}: Status -> completed based on round page.")

                batch.update(game_ref, update_data)
                updated_count += 1

            batch_count += 1
            if batch_count >= MAX_BATCH_SIZE: logger.info(f"Committing game batch ({batch_count} ops)..."); batch.commit(); batch = db.batch(); batch_count = 0

        except Exception as e:
            logger.error(f"Error processing game_id {game_id} in batch: {e}", exc_info=True)
            error_count += 1


    # Commit final batch
    if batch_count > 0: logger.info(f"Committing final game batch ({batch_count} ops)..."); batch.commit()
    logger.info(f"Firestore game update complete. Created: {created_count}, Updated: {updated_count}, Errors: {error_count}")


# ==================================
# Main Execution Logic
# ==================================
def main():
    start_time = time.time()
    logger.info(f"=== Fetch Round Games Script v{SCRIPT_VERSION} Starting ===")
    now_utc = datetime.now(timezone.utc)
    recheck_grade_threshold_utc = now_utc - timedelta(hours=GRADE_RECHECK_THRESHOLD_HOURS)

    try:
        # 1. Scrape main page & Process Comp/Grade Metadata (get list of grades to scan)
        grades_to_scan = scrape_and_process_main_page(db) # This also updates comp/grade metadata
        if not grades_to_scan: logger.warning("No grades identified for game scanning."); return

        # 2. Fetch all games from the rounds of selected grades (concurrently per grade)
        logger.info(f"--- Fetching Games from {len(grades_to_scan)} Grades (Round-by-Round) ---")
        all_parsed_games_dict = {} # Use dict keyed by game_id for automatic deduplication

        # Use ThreadPoolExecutor to fetch rounds for different grades concurrently
        # Note: Scraping rounds *within* a grade is sequential in fetch_and_process_grade_rounds
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT_WORKERS_ROUNDS) as executor:
            future_to_grade = {executor.submit(fetch_and_process_grade_rounds, grade_info, grade_ref, parent_comp_ref): grade_info for grade_info, grade_ref, parent_comp_ref in grades_to_scan}

            for future in concurrent.futures.as_completed(future_to_grade):
                grade_info = future_to_grade[future]
                try:
                    games_from_grade = future.result() # List of game dicts
                    for game_data in games_from_grade:
                        if game_data and 'game_id' in game_data:
                            # Add/overwrite in dict - ensures latest parse wins if somehow duplicated across grades
                            all_parsed_games_dict[game_data['game_id']] = game_data
                except Exception as exc:
                    logger.error(f"Grade {grade_info['fixture_id']} generated an exception during round processing: {exc}", exc_info=True)

        logger.info(f"Finished fetching rounds. Found {len(all_parsed_games_dict)} unique games across scanned grades.")

        # 3. Process (create/update) games in Firestore using batches
        if all_parsed_games_dict:
            create_update_games_in_batch(db, all_parsed_games_dict)
        else:
            logger.info("No new/updated game data found to process in Firestore.")

    except Exception as e:
        logger.error(f"An unexpected error occurred during the main script: {e}", exc_info=True)

    elapsed_time = time.time() - start_time
    logger.info(f"Script finished in {elapsed_time:.2f} seconds.")

if __name__ == "__main__":
    main()