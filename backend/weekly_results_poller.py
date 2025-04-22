import firebase_admin
from firebase_admin import credentials, firestore
import requests
from bs4 import BeautifulSoup
import re
import logging
import time
from datetime import datetime, timezone # Import timezone
import sys

# --- Configuration ---
CREDENTIALS_PATH = "./secrets/serviceAccountKey.json"  # Adjust path if needed
COLLECTION_NAME = "games"
BATCH_SIZE = 100  # Number of updates to batch together
REQUEST_TIMEOUT = 15  # Increased timeout for potentially slower pages
MAX_RETRIES = 3
RETRY_DELAY = 3  # Slightly longer delay
SLEEP_BETWEEN_SCRAPES = 0.5 # Seconds to wait between scraping attempts
DRY_RUN = False  # SET TO False TO ACTUALLY WRITE CHANGES TO FIRESTORE

# --- Logging Setup ---
log_filename = f"results_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s', # Added function name
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler() # Also print logs to console
    ]
)
logger = logging.getLogger(__name__)

# --- Firestore Initialization ---
try:
    logger.info(f"Initializing Firebase using credentials: {CREDENTIALS_PATH}")
    # Check if already initialized (useful if running parts of code multiple times)
    if not firebase_admin._apps:
        cred = credentials.Certificate(CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred)
    else:
        logger.info("Firebase app already initialized.")
    db = firestore.client()
    logger.info("Firestore client obtained.")
except Exception as e:
    logger.error(f"Failed to initialize Firebase: {e}", exc_info=True)
    sys.exit(1) # Exit if Firebase can't initialize

# --- Helper Functions ---
def make_request(url, retry_count=0):
    """Makes an HTTP GET request with retries."""
    try:
        logger.debug(f"Requesting URL: {url}")
        response = requests.get(url, timeout=REQUEST_TIMEOUT, headers={'User-Agent': 'Mozilla/5.0'}) # Add User-Agent
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        logger.debug(f"Request successful for: {url}")
        return response
    except requests.exceptions.Timeout:
        logger.warning(f"Request timed out for {url}.")
    except requests.exceptions.HTTPError as e:
        logger.warning(f"HTTP error {e.response.status_code} for {url}: {e}")
        # Don't retry on 404 Not Found, it likely means the game URL is wrong/old
        if e.response.status_code == 404:
            return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"Request failed for {url}: {e}")

    # Retry logic
    if retry_count < MAX_RETRIES:
        logger.warning(f"Retrying ({retry_count + 1}/{MAX_RETRIES})...")
        time.sleep(RETRY_DELAY * (retry_count + 1)) # Exponential backoff
        return make_request(url, retry_count + 1)
    else:
        logger.error(f"Request failed for {url} after {MAX_RETRIES} attempts.")
        return None

def scrape_game_results(game_url):
    """
    Scrapes the game detail page for scores and winner text.

    Args:
        game_url (str): The URL of the specific game detail page.

    Returns:
        dict: A dictionary containing 'home_score', 'away_score',
              and optionally 'winner_text', or None if scraping fails.
    """
    logger.info(f"Attempting to scrape results from: {game_url}")
    response = make_request(game_url)
    if not response:
        return None # Request failed

    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        results_data = {}

        # --- Score Extraction ---
        # Target: <h1 class="h2 mb-0"> 1 - 2 </h1> (example)
        score_element = soup.select_one('h1.h2.mb-0')
        if score_element:
            score_text = score_element.get_text(strip=True)
            logger.debug(f"Found score text: '{score_text}'")
            scores = [s.strip() for s in score_text.split('-')]
            if len(scores) == 2:
                try:
                    home_score = int(scores[0])
                    away_score = int(scores[1])
                    results_data['home_score'] = home_score
                    results_data['away_score'] = away_score
                    logger.info(f"Extracted scores: Home={home_score}, Away={away_score}")
                except ValueError:
                    logger.warning(f"Could not convert scores to integers from text: '{score_text}' in {game_url}. Storing raw text.")
                    # Store raw scores if conversion fails (e.g., 'W/O', 'F/F')
                    results_data['home_score_raw'] = scores[0]
                    results_data['away_score_raw'] = scores[1]
            else:
                logger.warning(f"Score text format unexpected: '{score_text}' in {game_url}")
        else:
            logger.warning(f"Score element (h1.h2.mb-0) not found on page: {game_url}")
            return None # Essential data missing

        # --- Winner Text Extraction (Optional) ---
        # Target: <h2 class="h4"> <a ...>Mentone Hockey Club</a> win! </h2>
        winner_element = soup.select_one('h2.h4') # This selector might need refinement if other h2.h4 exist
        if winner_element:
            winner_text = winner_element.get_text(strip=True)
            results_data['winner_text'] = winner_text
            logger.debug(f"Found winner text: '{winner_text}'")

        # Only return data if scores were found (either int or raw)
        if 'home_score' in results_data or 'home_score_raw' in results_data:
            return results_data
        else:
            logger.warning(f"No usable scores found on page: {game_url}")
            return None

    except Exception as e:
        logger.error(f"Error parsing HTML for {game_url}: {e}", exc_info=True)
        return None

# --- Main Migration Logic ---
def update_results_in_firestore():
    """
    Finds games needing results, scrapes them, and updates Firestore.
    """
    logger.info("Starting results update process...")
    if DRY_RUN:
        logger.warning("!!! DRY RUN MODE ENABLED. No changes will be written to Firestore. !!!")
    else:
        logger.warning("!!! LIVE RUN MODE. Changes WILL be written to Firestore. !!!")
        # time.sleep(3) # Optional safety pause for live run

    try:
        games_ref = db.collection(COLLECTION_NAME)
        now_utc = datetime.now(timezone.utc) # Use timezone-aware 'now' for comparison

        # Query for games in the past that are not yet completed and have a URL
        query = games_ref.where("date", "<", now_utc) \
            .where("status", "in", ["scheduled", "in_progress"])
        # Add .where("url", "!=", None) if some games might lack a URL

        logger.info("Querying Firestore for games needing results check...")
        docs_to_check = list(query.stream()) # Execute query and get all docs
        logger.info(f"Found {len(docs_to_check)} potential games to check.")

        if not docs_to_check:
            logger.info("No games found requiring results update at this time.")
            return

        processed_count = 0
        updated_count = 0
        failed_scrape_count = 0
        batch_count = 0
        batch = db.batch()
        start_time = time.time()

        for doc in docs_to_check:
            processed_count += 1
            game_data = doc.to_dict()
            doc_id = doc.id
            game_url = game_data.get('url')

            logger.debug(f"Processing game doc ID: {doc_id}")

            # Validate URL
            if not game_url or not game_url.startswith('http'):
                logger.warning(f"Skipping game {doc_id}: Invalid or missing URL ('{game_url}').")
                continue

            # --- Scrape Results ---
            scraped_results = scrape_game_results(game_url)

            if scraped_results:
                logger.info(f"Successfully scraped results for game {doc_id}.")
                update_payload = {
                    "status": "completed",
                    "results_retrieved_at": firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP
                }

                # Add scores (handle both int and raw string versions)
                if 'home_score' in scraped_results:
                    update_payload['home_team.score'] = scraped_results['home_score']
                elif 'home_score_raw' in scraped_results:
                    update_payload['home_team.score_raw'] = scraped_results['home_score_raw']
                    # Optionally clear integer score if raw is found later
                    update_payload['home_team.score'] = firestore.DELETE_FIELD

                if 'away_score' in scraped_results:
                    update_payload['away_team.score'] = scraped_results['away_score']
                elif 'away_score_raw' in scraped_results:
                    update_payload['away_team.score_raw'] = scraped_results['away_score_raw']
                    update_payload['away_team.score'] = firestore.DELETE_FIELD

                if 'winner_text' in scraped_results:
                    update_payload['winner_text'] = scraped_results['winner_text'] # Optional

                # Add update to batch
                doc_ref = games_ref.document(doc_id)
                batch.update(doc_ref, update_payload)
                batch_count += 1
                updated_count += 1
                logger.info(f"Prepared update for game {doc_id}: {update_payload}")

                # Commit batch if full
                if batch_count >= BATCH_SIZE:
                    if not DRY_RUN:
                        logger.info(f"Committing batch of {batch_count} updates...")
                        batch.commit()
                        logger.info("Batch committed.")
                    else:
                        logger.info(f"[DRY RUN] Would commit batch of {batch_count} updates.")
                    batch = db.batch() # Reset batch
                    batch_count = 0

            else:
                # Scraping failed or no results found yet
                failed_scrape_count += 1
                logger.warning(f"Failed to scrape or find results for game {doc_id} at {game_url}.")
                # Optionally, update a 'last_checked' timestamp even on failure
                # update_payload = {"results_last_checked_at": firestore.SERVER_TIMESTAMP}
                # batch.update(games_ref.document(doc_id), update_payload)
                # batch_count += 1 ... handle commit logic

            # Be nice to the server
            time.sleep(SLEEP_BETWEEN_SCRAPES)

        # Commit any remaining updates
        if batch_count > 0:
            if not DRY_RUN:
                logger.info(f"Committing final batch of {batch_count} updates...")
                batch.commit()
                logger.info("Final batch committed.")
            else:
                logger.info(f"[DRY RUN] Would commit final batch of {batch_count} updates.")

        # --- Summary ---
        end_time = time.time()
        total_time = end_time - start_time
        logger.info("--- Results Update Summary ---")
        logger.info(f"Total games checked: {processed_count} (out of {len(docs_to_check)} potential)")
        logger.info(f"Successful updates prepared/committed: {updated_count}")
        logger.info(f"Failed scrapes or no results found: {failed_scrape_count}")
        if DRY_RUN:
            logger.info(f"DRY RUN COMPLETE. No documents were actually updated.")
        else:
            logger.info(f"Update process complete.")
        logger.info(f"Total time taken: {total_time:.2f} seconds")

    except Exception as e:
        logger.error(f"An error occurred during the results update process: {e}", exc_info=True)

# --- Main Execution ---
if __name__ == "__main__":
    main_start_time = time.time()
    logger.info("================================================")
    logger.info(" Firestore Game Results Update Script Started ")
    logger.info("================================================")

    update_results_in_firestore()

    main_end_time = time.time()
    logger.info("================================================")
    logger.info(f" Script Finished in {main_end_time - main_start_time:.2f} seconds")
    logger.info("================================================")