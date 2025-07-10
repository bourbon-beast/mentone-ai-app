# update_results.py

import argparse
import sys
import re
import time
from datetime import datetime, timedelta # Keep timedelta
# from firebase_admin import firestore # Already imported at top level if needed
# ^ This will be available if your firebase_init imports it or if you import it directly

# Import utility modules
from backend.utils.firebase_init import initialize_firebase
from backend.utils.request_utils import make_request
from backend.utils.logging_utils import setup_logger
from backend.utils.parsing_utils import clean_text, extract_number

# Constants
BASE_URL = "https://www.hockeyvictoria.org.au"
# GAME_URL_TEMPLATE = "https://www.hockeyvictoria.org.au/games/game/{game_id}" # Not used if URL in game doc
GAME_URL_TEMPLATE = "https://www.hockeyvictoria.org.au/game/{game_id}" # Corrected template
DELAY_BETWEEN_REQUESTS = 1
DEFAULT_DAYS_BACK = 7
SCRIPT_VERSION = "1.1-results-update"

# --- Ensure firestore is available for SERVER_TIMESTAMP ---
# This should come from firebase_admin package
from firebase_admin import firestore

def update_game_result(logger, game_doc_data, session=None):
    """Update result for a specific game.
    Args:
        logger: Logger instance
        game_doc_data: Game dictionary from Firestore (includes 'id' as doc ID)
        session: Optional requests session
    Returns:
        dict or None: Updated fields for the game or None if no update
    """
    game_id = game_doc_data.get("id") # This is the Firestore document ID (string)
    # The actual numeric HV game ID might be stored under a different field if needed for URL
    # Let's assume 'id' field in the document *is* the HV game ID (numeric or string)
    # For URL construction, we need the numeric part if game_doc_data['id'] is string.
    # If game_doc_data['id'] is already numeric (from migration), str(game_id) is fine.
    hv_game_id_for_url = str(game_id)


    game_url = game_doc_data.get("url")
    if not game_url: # Construct if missing
        game_url = GAME_URL_TEMPLATE.format(game_id=hv_game_id_for_url)

    logger.info(f"Fetching results for game: {game_id} from: {game_url}")
    response = make_request(game_url, session=session, script_version=SCRIPT_VERSION)
    if not response:
        logger.error(f"Failed to get game page: {game_url}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    update_payload = {} # Store only fields that need updating
    home_score_val = None
    away_score_val = None
    winner_text_val = None
    status_changed = False

    # 1. Primary Score Extraction: <h1 class="h2 mb-0"> 1 - 2 </h1>
    score_h1 = soup.select_one("h1.h2.mb-0")
    if score_h1:
        score_text = score_h1.get_text(separator="-", strip=True)
        scores = [s.strip() for s in score_text.split('-')]
        if len(scores) == 2:
            try:
                home_score_val = int(scores[0])
                away_score_val = int(scores[1])
                logger.debug(f"Game {game_id}: Scores from h1: Home={home_score_val}, Away={away_score_val}")
                update_payload["status"] = "completed"
                status_changed = True
            except ValueError:
                logger.warning(f"Game {game_id}: Non-numeric scores in h1: '{score_text}'. Storing raw.")
                update_payload["home_team.score_raw"] = scores[0] # Using dot notation
                update_payload["away_team.score_raw"] = scores[1]
                update_payload["status"] = "completed" # Assume completed
                status_changed = True
        else:
            logger.warning(f"Game {game_id}: Unexpected score format in h1: '{score_text}'")

    # 2. Winner Text Extraction
    winner_element = soup.select_one('h2.h4') # Often "Team X win!" or "Teams drew!"
    if winner_element:
        winner_text_val = clean_text(winner_element.text)
        if winner_text_val:
            update_payload["winner_text"] = winner_text_val
            logger.debug(f"Game {game_id}: Winner text: '{winner_text_val}'")
            if not status_changed and update_payload.get("status") != "completed":
                update_payload["status"] = "completed" # If winner text, it's completed
                status_changed = True

    # 3. Forfeit/Cancelled Check (only if no scores yet and status not yet completed by above)
    if home_score_val is None and not status_changed:
        forfeit_terms = ["forfeit", "cancelled", "postponed", "abandoned", "washed out"]
        page_text_lower = soup.get_text().lower()
        for term in forfeit_terms:
            if term in page_text_lower:
                logger.info(f"Game {game_id}: Detected term '{term}'.")
                update_payload["status"] = term # Use the specific term as status
                status_changed = True
                # For forfeits, scores are often not explicitly listed, but result implies it
                if term == "forfeit":
                    # Try to determine which team forfeited (complex, often not clear)
                    # For now, just mark as forfeit, scores can remain None
                    # Or set a standard forfeit score if required by your app logic
                    # e.g., update_payload["home_team.score"] = 0; update_payload["away_team.score"] = 0;
                    pass
                break

    # If status changed to completed or a special status, add scores and result
    if status_changed and update_payload.get("status") in ["completed", "forfeit"]:
        if "home_team.score_raw" not in update_payload : # Only set numeric if not raw
            update_payload["home_team.score"] = home_score_val
        if "away_team.score_raw" not in update_payload:
            update_payload["away_team.score"] = away_score_val

        # Determine Mentone result if numeric scores are available
        if home_score_val is not None and away_score_val is not None:
            is_mentone_home_by_name = TEAM_FILTER_KEYWORD.lower() in game_doc_data.get("home_team", {}).get("name", "").lower()
            is_mentone_away_by_name = TEAM_FILTER_KEYWORD.lower() in game_doc_data.get("away_team", {}).get("name", "").lower()

            if is_mentone_home_by_name:
                if home_score_val > away_score_val: update_payload["mentone_result"] = "win"
                elif home_score_val < away_score_val: update_payload["mentone_result"] = "loss"
                else: update_payload["mentone_result"] = "draw"
            elif is_mentone_away_by_name:
                if away_score_val > home_score_val: update_payload["mentone_result"] = "win"
                elif away_score_val < home_score_val: update_payload["mentone_result"] = "loss"
                else: update_payload["mentone_result"] = "draw"

        logger.info(f"Game result for {game_id}: Status={update_payload['status']}, Home={home_score_val}, Away={away_score_val}")
        return update_payload # Return only the fields to update
    elif status_changed and update_payload.get("status") not in ["completed", "forfeit"]:
        # For 'cancelled', 'postponed' etc.
        logger.info(f"Game status for {game_id}: {update_payload['status']}")
        return {"status": update_payload["status"]} # Only update status
    else:
        # Game does not appear completed or status changed from this page
        logger.debug(f"Game {game_id}: No conclusive result/status change found on detail page.")
        # Consider 'unknown_outcome' logic from previous response if desired
        return None


def update_game_in_firestore(db, game_id_str, update_payload, dry_run=False):
    """Update a game in Firestore with the provided payload."""
    if not update_payload:
        logger.debug(f"No update payload for game {game_id_str}. Skipping Firestore write.")
        return False

    if dry_run:
        logger.info(f"[DRY RUN] Would update game {game_id_str} with: {update_payload}")
        return True
    try:
        game_ref = db.collection("games").document(game_id_str)
        # Add meta timestamps to every successful update from this script
        update_payload["updated_at"] = firestore.SERVER_TIMESTAMP
        update_payload["results_retrieved_at"] = firestore.SERVER_TIMESTAMP

        logger.debug(f"Updating game {game_id_str} in Firestore with: {update_payload}")
        game_ref.update(update_payload)
        return True
    except Exception as e:
        logger.error(f"Failed to update game (ID: {game_id_str}): {str(e)}", exc_info=True)
        return False

def find_games_to_update(db, days_back=DEFAULT_DAYS_BACK, game_id_filter=None):
    """Finds games that likely need their results updated."""
    games_to_update = []
    try:
        if game_id_filter:
            doc = db.collection("games").document(str(game_id_filter)).get()
            if doc.exists:
                game_data = doc.to_dict(); game_data["id"] = doc.id
                games_to_update.append(game_data)
            else: logger.error(f"Game not found with ID: {game_id_filter}")
        else:
            current_time_utc = datetime.now(timezone.utc)
            past_date_utc = current_time_utc - timedelta(days=days_back)
            logger.info(f"Querying for games scheduled between {past_date_utc.strftime('%Y-%m-%d')} and {current_time_utc.strftime('%Y-%m-%d')}")

            query = db.collection("games") \
                .where("mentone_playing", "==", True) \
                .where("date", ">=", past_date_utc) \
                .where("date", "<=", current_time_utc) \
                .where("status", "in", ["scheduled", "unknown_outcome", "postponed"]) # Add other statuses you want to re-check
            # .where("status", "==", "scheduled") # Simpler query

            for doc in query.stream():
                game_data = doc.to_dict(); game_data["id"] = doc.id
                games_to_update.append(game_data)
        logger.info(f"Found {len(games_to_update)} games to check for results.")
        return games_to_update
    except Exception as e:
        logger.error(f"Error finding games to update: {e}", exc_info=True)
        return []


def main():
    # ... (argparse and logger setup as before) ...
    parser = argparse.ArgumentParser(description="Update Hockey Victoria game results")
    parser.add_argument("--game-id", type=str, help="Specific game ID to update")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS_BACK, help=f"Days back (default: {DEFAULT_DAYS_BACK})")
    parser.add_argument("--dry-run", action="store_true", help="No DB writes")
    parser.add_argument("--creds", type=str, help="Path to Firebase creds")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()
    log_level = "DEBUG" if args.verbose else "INFO"; global logger; logger = setup_logger("update_results", log_level=log_level)

    try:
        db = initialize_firebase(args.creds) if not args.dry_run else None
        session = requests.Session()
        start_time = datetime.now()
        games_to_update = find_games_to_update(db, args.days, args.game_id)
        games_updated_count = 0; games_no_change_count = 0

        for game_doc_data in games_to_update:
            logger.info(f"Processing game: {game_doc_data.get('id')} - {game_doc_data.get('home_team', {}).get('name', 'N/A')} vs {game_doc_data.get('away_team', {}).get('name', 'N/A')}")
            update_payload = update_game_result(logger, game_doc_data, session) # game_doc_data already has 'id'

            if update_payload: # If there are fields to update
                if db: # Ensure db is not None (i.e., not dry_run)
                    success = update_game_in_firestore(db, str(game_doc_data['id']), update_payload, args.dry_run)
                    if success: games_updated_count += 1
                elif args.dry_run: # If dry_run, db is None, but we still count
                    logger.info(f"[DRY RUN] Would update game {game_doc_data['id']} with {update_payload}")
                    games_updated_count += 1
            else:
                logger.debug(f"No updates identified for game: {game_doc_data.get('id')}")
                games_no_change_count += 1
            time.sleep(DELAY_BETWEEN_REQUESTS)

        elapsed_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Results update completed in {elapsed_time:.2f} seconds. Updated: {games_updated_count}, No Change: {games_no_change_count}.")
        if args.dry_run: logger.info("DRY RUN - No database changes were made")
        return 0
    except Exception as e: logger.error(f"Error: {e}", exc_info=True); return 1

if __name__ == "__main__":
    sys.exit(main())