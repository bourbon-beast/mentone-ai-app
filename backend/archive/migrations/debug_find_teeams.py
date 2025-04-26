# fix_club_mentone_ids.py
#
# Purpose: One-time script to correct team documents that were erroneously
#          created with 'club_id: "club_mentone"' and incorrect club_ref.
#          It changes them to 'club_id: "mentone"' and points to 'clubs/mentone'.
#          Also deletes the 'clubs/club_mentone' document if it exists.

import firebase_admin
from firebase_admin import credentials, firestore
import logging
import time
from datetime import datetime
import os

# --- Basic Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s [%(funcName)s] - %(message)s',
    handlers=[
        logging.FileHandler(f"fix_club_mentone_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Constants ---
MAX_BATCH_SIZE = 400
SCRIPT_VERSION = "1.0-fix-club-mentone"

# --- Firebase Initialization ---
try:
    if not firebase_admin._apps:
        cred_path = os.path.join(os.path.dirname(__file__), '..', 'secrets', 'serviceAccountKey.json')
        if not os.path.exists(cred_path): cred_path = os.path.join('secrets', 'serviceAccountKey.json')
        if not os.path.exists(cred_path): raise FileNotFoundError("Cannot find serviceAccountKey.json")
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        logger.info(f"Firebase initialized using: {cred_path}")
    else: logger.info("Firebase app already initialized.")
    db = firestore.client()
except Exception as e:
    logger.error(f"Failed to initialize Firebase: {e}", exc_info=True)
    exit(1)

# --- Main Migration Logic ---
def fix_incorrect_club_ids():
    logger.info("Starting migration to fix 'club_mentone' IDs...")
    teams_ref = db.collection("teams")
    mentone_club_ref = db.collection("clubs").document("mentone") # The CORRECT ref

    # Query for teams with the incorrect club_id
    query = teams_ref.where("club_id", "==", "club_mentone")
    docs_to_fix = list(query.stream())

    if not docs_to_fix:
        logger.info("No teams found with club_id 'club_mentone'. No migration needed for teams.")
    else:
        logger.info(f"Found {len(docs_to_fix)} teams with incorrect club_id 'club_mentone'.")
        batch = db.batch()
        batch_count = 0
        updated_count = 0
        error_count = 0

        for doc in docs_to_fix:
            try:
                logger.info(f"Updating team {doc.id}...")
                update_payload = {
                    "club_id": "mentone",
                    "club_ref": mentone_club_ref,
                    "club": "Mentone Hockey Club", # Ensure full name is also correct
                    "updated_at": firestore.SERVER_TIMESTAMP
                }
                batch.update(doc.reference, update_payload)
                batch_count += 1
                updated_count += 1

                if batch_count >= MAX_BATCH_SIZE:
                    logger.info(f"Committing batch ({batch_count} updates)...")
                    batch.commit()
                    batch = db.batch(); batch_count = 0

            except Exception as e:
                logger.error(f"Failed to process team {doc.id} for club_id fix: {e}")
                error_count += 1

        # Commit final batch
        if batch_count > 0:
            logger.info(f"Committing final batch ({batch_count} updates)...")
            batch.commit()

        logger.info(f"Team Update Summary: Updated {updated_count}, Errors: {error_count}")

    # --- Delete incorrect club document ---
    try:
        incorrect_club_ref = db.collection("clubs").document("club_mentone")
        if incorrect_club_ref.get().exists:
            logger.info("Deleting incorrectly created club document 'club_mentone'...")
            incorrect_club_ref.delete()
            logger.info("Successfully deleted 'club_mentone'.")
        else:
            logger.info("Incorrect club 'club_mentone' not found, no deletion needed.")
    except Exception as e:
        logger.error(f"Failed to delete incorrect club 'club_mentone': {e}")


# --- Main Execution ---
if __name__ == "__main__":
    start_time = time.time()
    logger.info(f"=== Fix Incorrect Club ID Script v{SCRIPT_VERSION} Starting ===")
    logger.warning("This script ONLY corrects teams with 'club_id: club_mentone'. Ensure backup!")
    # confirm = input("Type 'FIX_CLUBID' to proceed: ")
    # if confirm != "FIX_CLUBID":
    #     logger.info("Migration cancelled.")
    #     exit()

    fix_incorrect_club_ids()

    elapsed_time = time.time() - start_time
    logger.info(f"Club ID fix script finished in {elapsed_time:.2f} seconds.")