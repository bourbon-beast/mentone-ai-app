# migrate_data_schema.py
#
# Purpose: One-time script to update existing Firestore documents (primarily teams)
#          to match the final desired schema conventions (numeric IDs inside, string ID field, etc.).
# Key Actions: Listed in the description above.
#
# Use Case: Run ONCE after previous script runs created inconsistencies.

import firebase_admin
from firebase_admin import credentials, firestore
import re
import logging
import time
from datetime import datetime, timezone
import os

# --- Basic Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s [%(funcName)s] - %(message)s',
    handlers=[
        logging.FileHandler(f"migrate_schema_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Constants ---
TEAM_FILTER_KEYWORD = "Mentone"
MAX_BATCH_SIZE = 400 # Firestore batch limit
SCRIPT_VERSION = "1.2-migration-final-schema" # Updated version

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
def migrate_teams_schema():
    """Iterates through teams and updates them to the final desired schema."""
    logger.info(f"Starting team data migration to schema v{SCRIPT_VERSION}...")
    teams_ref = db.collection("teams")
    all_teams_docs = list(teams_ref.stream()) # Fetch all team documents first
    logger.info(f"Fetched {len(all_teams_docs)} total team documents.")

    # Cache fetched grades data to reduce Firestore reads
    grade_cache = {}
    mentone_club_ref = db.collection("clubs").document("mentone") # Correct Mentone club ref

    batch = db.batch()
    batch_count = 0
    updated_count = 0
    mentone_updated_count = 0
    skipped_count = 0
    error_count = 0

    for team_doc in all_teams_docs:
        try:
            team_data = team_doc.to_dict()
            if not team_data: # Skip if data is missing (shouldn't happen often)
                logger.warning(f"Team document {team_doc.id} has no data. Skipping.")
                skipped_count += 1
                continue

            team_ref = team_doc.reference
            doc_id_str = team_doc.id # This is the correct string team ID (e.g., "337086")

            is_mentone_team = team_data.get('is_home_club', False) or \
                              team_data.get('club_id') == 'mentone' or \
                              team_data.get('club_id') == 'club_mentone' or \
                              TEAM_FILTER_KEYWORD.lower() in team_data.get('name', '').lower()

            update_payload = {}
            needs_update = False

            # --- Field Checks & Updates ---

            # 1. Ensure internal 'id' field is STRING matching doc ID
            internal_id = team_data.get('id')
            if internal_id != doc_id_str: # Check if it's missing or different (number or wrong string)
                update_payload['id'] = doc_id_str # Set to STRING document ID
                needs_update = True
                logger.debug(f"Team {doc_id_str}: Fixing internal 'id' field to string '{doc_id_str}'.")

            # 2. Ensure 'fixture_id' is NUMBER
            fixture_id_val = team_data.get('fixture_id')
            target_fixture_id_num = None
            if isinstance(fixture_id_val, str):
                try: target_fixture_id_num = int(fixture_id_val); update_payload['fixture_id'] = target_fixture_id_num; needs_update = True; logger.debug(f"Team {doc_id_str}: Fixing 'fixture_id' to numeric {target_fixture_id_num}.")
                except (ValueError, TypeError): logger.warning(f"Team {doc_id_str}: Invalid fixture_id '{fixture_id_val}'. Cannot convert.")
            elif isinstance(fixture_id_val, int): target_fixture_id_num = fixture_id_val # Already correct type
            elif fixture_id_val is None and 'fixture_id' in team_data: target_fixture_id_num = None # Keep None if explicitly None
            # If field is missing, we'll try to add it later if grade_ref exists

            # 3. Ensure 'comp_id' is NUMBER
            comp_id_val = team_data.get('comp_id')
            target_comp_id_num = None
            if isinstance(comp_id_val, str):
                try: target_comp_id_num = int(comp_id_val); update_payload['comp_id'] = target_comp_id_num; needs_update = True; logger.debug(f"Team {doc_id_str}: Fixing 'comp_id' to numeric {target_comp_id_num}.")
                except (ValueError, TypeError): logger.warning(f"Team {doc_id_str}: Invalid comp_id '{comp_id_val}'. Cannot convert.")
            elif isinstance(comp_id_val, int): target_comp_id_num = comp_id_val # Already correct type
            elif comp_id_val is None and 'comp_id' in team_data: target_comp_id_num = None # Keep None if explicitly None

            # 4. Remove 'hv_team_id' field
            if 'hv_team_id' in team_data:
                update_payload['hv_team_id'] = firestore.DELETE_FIELD; needs_update = True
                logger.debug(f"Team {doc_id_str}: Removing redundant 'hv_team_id'.")

            # 5. Ensure 'active' field exists (default true)
            if 'active' not in team_data:
                update_payload['active'] = True; needs_update = True
                logger.debug(f"Team {doc_id_str}: Adding missing 'active' field (set to true).")

            # --- Mentone-Specific Field Checks ---
            if is_mentone_team:
                # 6. Fix 'club_id', 'club_ref', 'club'
                if team_data.get('club_id') != 'mentone':
                    update_payload['club_id'] = 'mentone'; needs_update = True
                    logger.debug(f"Team {doc_id_str}: Fixing club_id to 'mentone'.")
                if team_data.get('club_ref') != mentone_club_ref:
                    update_payload['club_ref'] = mentone_club_ref; needs_update = True
                    logger.debug(f"Team {doc_id_str}: Fixing club_ref.")
                if team_data.get('club') != 'Mentone Hockey Club':
                    update_payload['club'] = 'Mentone Hockey Club'; needs_update = True
                    logger.debug(f"Team {doc_id_str}: Fixing club name.")
                if not team_data.get('is_home_club'): # Ensure is_home_club is true
                    update_payload['is_home_club'] = True; needs_update = True

                # Fetch Grade data (cached) if needed
                grade_data = None
                fixture_id_for_lookup = target_fixture_id_num # Use the numeric version
                if fixture_id_for_lookup:
                    fixture_id_for_lookup_str = str(fixture_id_for_lookup)
                    if fixture_id_for_lookup_str in grade_cache: grade_data = grade_cache[fixture_id_for_lookup_str]
                    else:
                        try:
                            grade_doc = db.collection("grades").document(fixture_id_for_lookup_str).get()
                            grade_data = grade_doc.to_dict() if grade_doc.exists else None
                            grade_cache[fixture_id_for_lookup_str] = grade_data
                            if grade_data is None: logger.warning(f"Grade document {fixture_id_for_lookup_str} not found for team {doc_id_str}")
                        except Exception as e: logger.error(f"Error fetching grade {fixture_id_for_lookup_str}: {e}"); grade_cache[fixture_id_for_lookup_str] = None

                # 7. Fix 'name' and 'comp_name' using Grade data
                if grade_data and 'name' in grade_data:
                    grade_name = grade_data['name']
                    grade_name_base = re.sub(r'\s*-\s*\d{4}$', '', grade_name).strip()
                    target_team_name = f"Mentone - {grade_name_base}" # Descriptive team name
                    target_comp_name = grade_name # Full grade name

                    if team_data.get('name') != target_team_name: update_payload['name'] = target_team_name; needs_update = True; logger.debug(f"Team {doc_id_str}: Fixing team 'name'.")
                    if team_data.get('comp_name') != target_comp_name: update_payload['comp_name'] = target_comp_name; needs_update = True; logger.debug(f"Team {doc_id_str}: Fixing 'comp_name'.")
                elif fixture_id_for_lookup: logger.warning(f"Cannot check/fix names for team {doc_id_str} as grade data for {fixture_id_for_lookup} is missing.")

                # 8. Add 'grade_ref' if missing
                if fixture_id_for_lookup and 'grade_ref' not in team_data:
                    update_payload['grade_ref'] = db.collection("grades").document(str(fixture_id_for_lookup)); needs_update = True
                    logger.debug(f"Team {doc_id_str}: Adding missing 'grade_ref'.")

                # 9. Add 'competition_ref' if missing
                comp_id_for_lookup = target_comp_id_num # Use numeric version
                if comp_id_for_lookup and 'competition_ref' not in team_data:
                    update_payload['competition_ref'] = db.collection("competitions").document(str(comp_id_for_lookup)); needs_update = True
                    logger.debug(f"Team {doc_id_str}: Adding missing 'competition_ref'.")

                # 10. Add 'mentone_playing' if missing
                if 'mentone_playing' not in team_data:
                    update_payload['mentone_playing'] = True; needs_update = True
                    logger.debug(f"Team {doc_id_str}: Adding missing 'mentone_playing'.")

                # 11. Initialize Ladder Fields if missing
                if 'ladder_position' not in team_data: update_payload['ladder_position'] = None; needs_update = True; logger.debug(f"Team {doc_id_str}: Initializing 'ladder_position'.")
                if 'ladder_points' not in team_data: update_payload['ladder_points'] = None; needs_update = True; logger.debug(f"Team {doc_id_str}: Initializing 'ladder_points'.")
                if 'ladder_updated_at' not in team_data: update_payload['ladder_updated_at'] = None; needs_update = True; logger.debug(f"Team {doc_id_str}: Initializing 'ladder_updated_at'.")

            # --- Perform Update if Needed ---
            if needs_update:
                logger.info(f"Updating team {doc_id_str} ('{team_data.get('name', 'N/A')}')")
                update_payload['updated_at'] = firestore.SERVER_TIMESTAMP
                batch.update(team_ref, update_payload)
                batch_count += 1
                updated_count += 1
                if is_mentone_team: mentone_updated_count += 1
            else:
                skipped_count += 1

            # Commit batch periodically
            if batch_count >= MAX_BATCH_SIZE:
                logger.info(f"Committing batch ({batch_count} updates)...")
                batch.commit()
                batch = db.batch(); batch_count = 0

        except Exception as e:
            logger.error(f"Failed to process team {team_doc.id}: {e}", exc_info=True)
            error_count += 1

    # Commit final batch
    if batch_count > 0:
        logger.info(f"Committing final batch ({batch_count} updates)...")
        batch.commit()

    # --- Delete incorrect club document ---
    try:
        incorrect_club_ref = db.collection("clubs").document("club_mentone")
        if incorrect_club_ref.get().exists:
            logger.info("Deleting incorrectly created club document 'club_mentone'...")
            incorrect_club_ref.delete()
            logger.info("Deleted 'club_mentone'.")
        else:
            logger.info("Incorrect club 'club_mentone' not found, no deletion needed.")
    except Exception as e:
        logger.error(f"Failed to delete incorrect club 'club_mentone': {e}")


    logger.info("--- Migration Summary ---")
    logger.info(f"Processed: {len(all_teams_docs)} teams")
    logger.info(f"Updated:   {updated_count} teams ({mentone_updated_count} Mentone teams)")
    logger.info(f"Skipped:   {skipped_count} teams (no changes needed)")
    logger.info(f"Errors:    {error_count}")

# --- Main Execution ---
if __name__ == "__main__":
    start_time = time.time()
    logger.info(f"=== Team Schema Migration Script v{SCRIPT_VERSION} Starting ===")
    logger.warning("This script will modify existing team documents. Ensure you have a backup!")
    # Optional: Confirmation prompt
    # confirm = input("This script modifies data. Type 'MIGRATE' to proceed: ")
    # if confirm != "MIGRATE":
    #     logger.info("Migration cancelled by user.")
    #     exit()

    migrate_teams_schema()

    elapsed_time = time.time() - start_time
    logger.info(f"Migration script finished in {elapsed_time:.2f} seconds.")