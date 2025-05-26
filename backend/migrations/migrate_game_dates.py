"""
Migration script to adjust game dates in Firestore.

This script fetches all games from the 'games' collection and subtracts 10 hours
from their 'date' field. This is intended to correct dates that might have been
incorrectly stored or interpreted with a +10 hour offset.

Usage:
    python -m backend.migrations.migrate_game_dates --creds <path_to_creds.json> [--dry-run] [-v]
"""
import argparse
import sys
from datetime import datetime, timedelta
import pytz # Though not strictly needed for subtraction if dates are already UTC

# Assuming the script is run from the root of the project or the backend module is in PYTHONPATH
try:
    from backend.utils.firebase_init import initialize_firebase
    from backend.utils.logging_utils import setup_logger
except ModuleNotFoundError:
    # If running script directly for testing and backend is not in path,
    # adjust sys.path. This is a common pattern for standalone scripts.
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from backend.utils.firebase_init import initialize_firebase
    from backend.utils.logging_utils import setup_logger

# Global logger instance
logger = None

def migrate_games(db, logger, dry_run=False):
    """
    Fetches games from Firestore and adjusts their 'date' field by subtracting 10 hours.

    Args:
        db: Firestore client instance.
        logger: Logger instance for logging messages.
        dry_run (bool): If True, simulate migration without actual database writes.
    """
    logger.info("Starting game date migration...")
    if dry_run:
        logger.info("DRY RUN mode activated. No changes will be written to the database.")

    games_collection_ref = db.collection("games")
    
    batch = db.batch()
    migrated_count = 0
    processed_count = 0
    batch_operation_count = 0 # Count operations in the current batch

    try:
        for game_doc in games_collection_ref.stream():
            processed_count += 1
            logger.debug(f"Processing game ID: {game_doc.id}")

            game_data = game_doc.to_dict()
            current_date_utc = game_data.get("date")

            if not current_date_utc:
                logger.warning(f"Game ID: {game_doc.id} - 'date' field is missing or None. Skipping.")
                continue

            if not isinstance(current_date_utc, datetime):
                logger.error(f"Game ID: {game_doc.id} - 'date' field is not a datetime object. Type: {type(current_date_utc)}. Skipping.")
                continue
            
            # Ensure the datetime is UTC if it's naive (Firestore Timestamps are usually UTC)
            if current_date_utc.tzinfo is None or current_date_utc.tzinfo.utcoffset(current_date_utc) is None:
                logger.debug(f"Game ID: {game_doc.id} - Date was naive, localizing to UTC.")
                current_date_utc = pytz.utc.localize(current_date_utc)
            else:
                # If already timezone-aware, ensure it's converted to UTC for consistent operations
                current_date_utc = current_date_utc.astimezone(pytz.utc)


            corrected_date_utc = current_date_utc - timedelta(hours=10)

            logger.info(f"Game ID: {game_doc.id} - Old date (UTC): {current_date_utc.isoformat()} -> New date (UTC): {corrected_date_utc.isoformat()}")

            if not dry_run:
                batch.update(game_doc.reference, {"date": corrected_date_utc})
                batch_operation_count += 1
                migrated_count +=1 # Count as migrated only if not dry_run and update is added to batch

                if batch_operation_count >= 400: # Firestore batch limit is 500, using 400 as a safe threshold
                    logger.info(f"Committing batch of {batch_operation_count} updates...")
                    batch.commit()
                    logger.info("Batch committed successfully.")
                    batch = db.batch() # Start a new batch
                    batch_operation_count = 0
            else:
                # In dry_run, we still increment migrated_count to show what *would* have been done
                migrated_count +=1


        if not dry_run and batch_operation_count > 0:
            logger.info(f"Committing final batch of {batch_operation_count} updates...")
            batch.commit()
            logger.info("Final batch committed successfully.")

        logger.info(f"Migration complete. Processed: {processed_count} documents.")
        if dry_run:
            logger.info(f"DRY RUN: Would have migrated {migrated_count} documents.")
        else:
            logger.info(f"Successfully migrated {migrated_count} documents.")

    except Exception as e:
        logger.error(f"An error occurred during migration: {e}", exc_info=True)
        if not dry_run and batch_operation_count > 0:
             logger.warning("There were pending operations in the batch that were not committed due to the error.")


def main():
    global logger # Allow main to assign to the global logger

    parser = argparse.ArgumentParser(description="Migrate game dates in Firestore by subtracting 10 hours.")
    parser.add_argument(
        "--creds",
        type=str,
        required=False, # Not strictly required if dry_run is True and DB connection is skipped
        help="Path to the Firebase credentials JSON file."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without actual database writes."
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (DEBUG level) logging."
    )

    args = parser.parse_args()

    log_level = "DEBUG" if args.verbose else "INFO"
    logger = setup_logger("migrate_game_dates", log_level=log_level)

    if not args.creds and not args.dry_run:
        logger.error("Firebase credentials path (--creds) is required when not in dry-run mode.")
        sys.exit(1)
    
    db = None
    if args.creds:
        try:
            logger.info(f"Initializing Firebase with credentials from: {args.creds}")
            db = initialize_firebase(args.creds)
            logger.info("Firebase initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}", exc_info=True)
            sys.exit(1)
    elif not args.dry_run: # Should have already exited above, but as a safeguard
        logger.error("Firebase credentials must be provided if not a dry run.")
        sys.exit(1)
    else:
        logger.info("Dry run mode: Firebase will not be initialized (no DB connection).")
        # For a more realistic dry run, we'd connect, but this allows testing logic without creds.
        # However, the current migrate_games expects a db object.
        # If we want a true simulation without db, migrate_games would need adjustment or a mock db.
        # For now, let's assume --creds should be provided for dry-run too, to fetch data.
        # The prompt implies fetching for dry run.
        logger.error("For a realistic dry run that fetches data, --creds should still be provided. Exiting.")
        sys.exit(1)


    if not db: # This check will now catch if --creds wasn't provided for a dry_run that needs to fetch.
        logger.error("Database client not initialized. Cannot proceed.")
        sys.exit(1)

    try:
        migrate_games(db, logger, args.dry_run)
    except Exception as e:
        logger.error(f"An unexpected error occurred in main: {e}", exc_info=True)
        sys.exit(1)
    
    logger.info("Script finished.")
    sys.exit(0)

if __name__ == "__main__":
    main()
