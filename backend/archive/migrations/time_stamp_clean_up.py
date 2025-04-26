# migrate_timezone_fix_simple.py
#
# Purpose: One-time script to convert timezone-aware datetime objects
#          in the 'date' field of the 'games' collection to naive datetime objects
#          using a document-set approach rather than batch update.

import firebase_admin
from firebase_admin import credentials, firestore
import logging
from datetime import datetime
import os
import time
import sys

# --- Configuration Settings ---
# Set to True to only log what would happen without making changes
DRY_RUN = False

# --- Basic Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s [%(funcName)s] - %(message)s',
    handlers=[
        logging.FileHandler(f"migrate_timestamps_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Firebase Initialization ---
try:
    # Try different common paths for the service account key
    cred_path = os.path.join(os.path.dirname(__file__), '..', 'secrets', 'serviceAccountKey.json')
    if not os.path.exists(cred_path):
        cred_path = os.path.join('secrets', 'serviceAccountKey.json')
    if not os.path.exists(cred_path):
        cred_path = 'serviceAccountKey.json'
    if not os.path.exists(cred_path):
        raise FileNotFoundError("Cannot find serviceAccountKey.json in any standard location.")

    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    logger.info(f"Firebase initialized using: {cred_path}")
    db = firestore.client()
except Exception as e:
    logger.error(f"Failed to initialize Firebase: {e}", exc_info=True)
    sys.exit(1)

# --- Helper Functions ---
def create_standard_datetime(dt):
    """Create a standard naive datetime object from any datetime by extracting components."""
    if not dt:
        return None

    # Extract components from original datetime
    return datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, dt.microsecond)

def migrate_timestamps():
    """Update games with timezone-aware dates to use naive datetimes."""
    logger.info(f"{'[DRY RUN] ' if DRY_RUN else ''}Starting timestamp migration process...")

    # Query for all game documents
    games_ref = db.collection("games")
    all_games_docs = list(games_ref.stream())
    logger.info(f"Fetched {len(all_games_docs)} total games.")

    updated_count = 0
    skipped_count = 0
    error_count = 0

    for game_doc in all_games_docs:
        try:
            game_data = game_doc.to_dict()
            game_ref = game_doc.reference
            game_id = game_doc.id

            if not game_data or 'date' not in game_data:
                skipped_count += 1
                continue

            current_date = game_data['date']

            # Check if it's a datetime object and if it has timezone info
            if isinstance(current_date, datetime) and current_date.tzinfo is not None:
                # Create a standard naive datetime with the same components
                naive_date = create_standard_datetime(current_date)

                logger.info(f"Game {game_id}: Converting timestamp {current_date} -> {naive_date}")

                # Update the document (unless in dry run mode)
                if not DRY_RUN:
                    game_ref.set({
                        'date': naive_date,
                        'updated_at': firestore.SERVER_TIMESTAMP
                    }, merge=True)

                    # Small delay between updates
                    time.sleep(0.05)

                updated_count += 1
            else:
                skipped_count += 1

        except Exception as e:
            logger.error(f"Failed to process game {game_doc.id}: {e}", exc_info=True)
            error_count += 1

    # Print summary
    logger.info("--- Migration Summary ---")
    logger.info(f"Processed: {len(all_games_docs)} games")

    if DRY_RUN:
        logger.info(f"DRY RUN: Would have updated {updated_count} games")
    else:
        logger.info(f"Updated: {updated_count} games")

    logger.info(f"Skipped: {skipped_count} games")
    logger.info(f"Errors:  {error_count}")

# --- Main Execution ---
if __name__ == "__main__":
    start_time = time.time()
    logger.info(f"{'[DRY RUN] ' if DRY_RUN else ''}Timestamp Migration Starting")

    if DRY_RUN:
        logger.warning("Running in DRY RUN mode - No actual changes will be made to the database")
        logger.warning("Set DRY_RUN = False at the top of the script to make actual changes")
    else:
        logger.warning("LIVE RUN MODE - Changes WILL be made to the database!")

    migrate_timestamps()

    elapsed_time = time.time() - start_time
    logger.info(f"Script completed in {elapsed_time:.2f} seconds.")