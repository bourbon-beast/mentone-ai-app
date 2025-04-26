import firebase_admin
from firebase_admin import credentials, firestore
import logging
from datetime import datetime
import time
import sys

# --- Configuration ---
CREDENTIALS_PATH = "../../secrets/serviceAccountKey.json"  # Adjust path if needed
COLLECTION_NAME = "games"
BATCH_SIZE = 200  # Process documents in batches for efficiency
DRY_RUN = False  # SET TO False TO ACTUALLY WRITE CHANGES TO FIRESTORE

# Configure logging
log_filename = f"migration_mentone_playing_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler() # Also print logs to console
    ]
)
logger = logging.getLogger(__name__)

# --- Firestore Initialization ---
try:
    logger.info(f"Initializing Firebase using credentials: {CREDENTIALS_PATH}")
    cred = credentials.Certificate(CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    logger.info("Firebase initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize Firebase: {e}", exc_info=True)
    sys.exit(1) # Exit if Firebase can't initialize

# --- Migration Logic ---
def check_mentone_playing(game_data):
    """Checks if Mentone is the home or away team."""
    is_playing = False
    try:
        home_club = game_data.get("home_team", {}).get("club")
        away_club = game_data.get("away_team", {}).get("club")

        if home_club and home_club.lower() == "mentone":
            is_playing = True
        elif away_club and away_club.lower() == "mentone":
            is_playing = True

    except Exception as e:
        logger.error(f"Error processing game data structure: {e}. Data: {game_data}")
        # Decide how to handle malformed data, e.g., default to False or skip
        return None # Indicate an error occurred during check

    return is_playing

def migrate_games_collection():
    """Iterates through the games collection and adds the mentone_playing field."""
    logger.info(f"Starting migration for collection: '{COLLECTION_NAME}'")
    if DRY_RUN:
        logger.warning("!!! DRY RUN MODE ENABLED. No changes will be written to Firestore. !!!")
    else:
        logger.warning("!!! LIVE RUN MODE. Changes WILL be written to Firestore. !!!")
        time.sleep(3) # Give user a moment to cancel if live run was accidental

    try:
        games_ref = db.collection(COLLECTION_NAME)
        docs_stream = games_ref.stream() # Use stream for large collections

        processed_count = 0
        updated_count = 0
        error_count = 0
        batch_count = 0
        batch = db.batch()

        start_time = time.time()

        for doc in docs_stream:
            processed_count += 1
            game_data = doc.to_dict()
            doc_id = doc.id

            # Check if the field already exists to avoid unnecessary writes
            if "mentone_playing" in game_data:
                # logger.debug(f"Skipping document '{doc_id}': 'mentone_playing' field already exists.")
                continue

            mentone_playing_value = check_mentone_playing(game_data)

            if mentone_playing_value is None:
                logger.error(f"Could not determine 'mentone_playing' for doc '{doc_id}'. Skipping update.")
                error_count += 1
                continue # Skip this document if check failed

            # Add update operation to the batch
            doc_ref = games_ref.document(doc_id)
            batch.update(doc_ref, {"mentone_playing": mentone_playing_value})
            batch_count += 1
            updated_count += 1
            # logger.info(f"Doc ID: {doc_id} -> Setting mentone_playing: {mentone_playing_value}")


            # Commit the batch when it reaches the BATCH_SIZE or if it's the last iteration (though stream doesn't easily tell last)
            if batch_count >= BATCH_SIZE:
                if not DRY_RUN:
                    logger.info(f"Committing batch of {batch_count} updates...")
                    batch.commit()
                    logger.info("Batch committed.")
                else:
                    logger.info(f"[DRY RUN] Would commit batch of {batch_count} updates.")

                # Reset batch
                batch = db.batch()
                batch_count = 0

            # Log progress periodically
            if processed_count % 500 == 0:
                elapsed_time = time.time() - start_time
                logger.info(f"Processed {processed_count} documents... ({elapsed_time:.2f}s elapsed)")


        # Commit any remaining updates in the last batch
        if batch_count > 0:
            if not DRY_RUN:
                logger.info(f"Committing final batch of {batch_count} updates...")
                batch.commit()
                logger.info("Final batch committed.")
            else:
                logger.info(f"[DRY RUN] Would commit final batch of {batch_count} updates.")


        end_time = time.time()
        total_time = end_time - start_time
        logger.info("--- Migration Summary ---")
        logger.info(f"Total documents processed: {processed_count}")
        logger.info(f"Total documents requiring update: {updated_count}")
        logger.info(f"Documents skipped (already had field or error): {processed_count - updated_count}")
        logger.info(f"Errors encountered during check: {error_count}")
        if DRY_RUN:
            logger.info(f"DRY RUN COMPLETE. No documents were actually updated.")
        else:
            logger.info(f"Migration complete. {updated_count} documents updated.")
        logger.info(f"Total time taken: {total_time:.2f} seconds")

    except Exception as e:
        logger.error(f"An error occurred during migration: {e}", exc_info=True)

# --- Main Execution ---
if __name__ == "__main__":
    main_start_time = time.time()
    logger.info("================================================")
    logger.info(" Firestore Games Migration Script Started")
    logger.info("================================================")

    migrate_games_collection()

    main_end_time = time.time()
    logger.info("================================================")
    logger.info(f" Script Finished in {main_end_time - main_start_time:.2f} seconds")
    logger.info("================================================")