"""
Hockey Victoria Results Update Script

This script updates game results by:
1. Finding scheduled games that have already been played
2. Scraping result data from Hockey Victoria website
3. Updating game status and score information in Firestore

Usage:
    python -m backend.scripts.update_results [--game-id GAME_ID] [--days DAYS] [--dry-run] [--creds CREDS_PATH] [--verbose]
"""

import argparse
import sys
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# Import utility modules
from backend.utils.firebase_init import initialize_firebase
from backend.utils.request_utils import make_request, build_url
from backend.utils.logging_utils import setup_logger
from backend.utils.parsing_utils import clean_text, extract_number

# Constants
BASE_URL = "https://www.hockeyvictoria.org.au"
GAME_URL_TEMPLATE = "https://www.hockeyvictoria.org.au/games/game/{game_id}"
DELAY_BETWEEN_REQUESTS = 1  # seconds
DEFAULT_DAYS_BACK = 7  # days

def update_game_result(logger, game, session=None):
    """Update result for a specific game.

    Args:
        logger: Logger instance
        game: Game dictionary with id and url
        session: Optional requests session

    Returns:
        dict or None: Updated game dictionary or None if no update
    """
    game_id = game.get("id")
    game_url = game.get("url")

    # If no URL, try constructing it
    if not game_url and game_id:
        game_url = GAME_URL_TEMPLATE.format(game_id=game_id)

    if not game_url:
        logger.error(f"No URL available for game: {game_id}")
        return None

    logger.info(f"Fetching results for game: {game_id} from: {game_url}")

    # Get game details page
    response = make_request(game_url, session=session)
    if not response:
        logger.error(f"Failed to get game page: {game_url}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # Check if the game has been played
    # Usually there's a results section or score displayed prominently

    # Try to find score elements
    score_elements = soup.select(".game-score, .match-score, .score, .result")

    if not score_elements:
        # Try looking for score in the header or title
        header_elements = soup.select("h1, h2, h3, h4")
        for header in header_elements:
            # Look for a score pattern like "Team A 3 - 2 Team B"
            score_match = re.search(r'(\d+)\s*[-:]\s*(\d+)', header.text)
            if score_match:
                score_elements = [header]
                break

    # If still no score elements, try a broader approach
    if not score_elements:
        # Look for any element with text containing digits separated by a dash
        all_elements = soup.select("div, p, span, td")
        for element in all_elements:
            score_match = re.search(r'(\d+)\s*[-:]\s*(\d+)', element.text)
            if score_match:
                score_elements = [element]
                break

    # If no score elements found, game may not have been played yet
    if not score_elements:
        # Check if there's any indication that the game was played
        result_indicators = ["final score", "result", "match complete", "full time"]
        page_text = soup.get_text().lower()

        if any(indicator in page_text for indicator in result_indicators):
            logger.warning(f"Game appears to be completed but no score found: {game_id}")
            # We'll mark it as completed but with no score
            return {
                **game,
                "status": "completed",
                "home_team": {
                    **(game.get("home_team", {})),
                    "score": None
                },
                "away_team": {
                    **(game.get("away_team", {})),
                    "score": None
                },
                "updated_at": datetime.now()
            }
        else:
            logger.debug(f"Game does not appear to be completed yet: {game_id}")
            return None

    # Extract scores from the found elements
    home_score = None
    away_score = None

    for element in score_elements:
        element_text = element.text.strip()

        # Try to extract scores with regex
        score_match = re.search(r'(\d+)\s*[-:]\s*(\d+)', element_text)
        if score_match:
            home_score = int(score_match.group(1))
            away_score = int(score_match.group(2))
            break

    # If we still don't have scores, try more specific elements
    if home_score is None or away_score is None:
        # Some sites have specific elements for home and away scores
        home_score_elem = soup.select_one(".home-score, .home-team-score")
        away_score_elem = soup.select_one(".away-score, .away-team-score")

        if home_score_elem and away_score_elem:
            home_score = extract_number(home_score_elem.text, None)
            away_score = extract_number(away_score_elem.text, None)

    # If scores are still not found, look for more complex structures
    if home_score is None or away_score is None:
        # Try to find a table with team names and scores
        tables = soup.select("table")
        for table in tables:
            rows = table.select("tr")
            for row in rows:
                cells = row.select("td")
                if len(cells) >= 2:
                    # Check if this row contains team names that match
                    home_team_name = game.get("home_team", {}).get("name", "").lower()
                    away_team_name = game.get("away_team", {}).get("name", "").lower()

                    row_text = row.text.lower()
                    if home_team_name in row_text and away_team_name in row_text:
                        # This row likely contains the match result
                        # Extract numbers from this row
                        numbers = re.findall(r'\d+', row_text)
                        if len(numbers) >= 2:
                            home_score = int(numbers[0])
                            away_score = int(numbers[1])
                            break

            if home_score is not None and away_score is not None:
                break

    # If we still don't have scores, check for forfeit or cancellation
    if home_score is None or away_score is None:
        forfeit_terms = ["forfeit", "cancelled", "postponed", "abandoned"]
        page_text = soup.get_text().lower()

        game_status = "completed"  # Default status

        for term in forfeit_terms:
            if term in page_text:
                if term == "forfeit":
                    game_status = "forfeit"
                    # Try to determine which team forfeited and assign scores accordingly
                    home_team_name = game.get("home_team", {}).get("name", "").lower()
                    away_team_name = game.get("away_team", {}).get("name", "").lower()

                    forfeit_context = re.search(r'(\w+\s+\w+)\s+forfeit', page_text)
                    if forfeit_context:
                        forfeiting_text = forfeit_context.group(1).lower()
                        if home_team_name in forfeiting_text:
                            home_score = 0
                            away_score = 3  # Default forfeit score
                        elif away_team_name in forfeiting_text:
                            home_score = 3  # Default forfeit score
                            away_score = 0
                        else:
                            # Can't determine which team forfeited
                            home_score = 0
                            away_score = 0
                else:
                    game_status = term  # cancelled, postponed, or abandoned
                    home_score = None
                    away_score = None
                break

    # Update the game with results
    updated_game = {
        **game,
        "status": game.get("status", "scheduled") if home_score is None and away_score is None else "completed",
        "home_team": {
            **(game.get("home_team", {})),
            "score": home_score
        },
        "away_team": {
            **(game.get("away_team", {})),
            "score": away_score
        },
        "updated_at": datetime.now()
    }

    # Check if we need to set mentone_result
    if updated_game["status"] == "completed" and home_score is not None and away_score is not None:
        home_is_mentone = game.get("home_team", {}).get("club") == "Mentone"
        away_is_mentone = game.get("away_team", {}).get("club") == "Mentone"

        if home_is_mentone:
            if home_score > away_score:
                updated_game["mentone_result"] = "win"
            elif home_score < away_score:
                updated_game["mentone_result"] = "loss"
            else:
                updated_game["mentone_result"] = "draw"
        elif away_is_mentone:
            if away_score > home_score:
                updated_game["mentone_result"] = "win"
            elif away_score < home_score:
                updated_game["mentone_result"] = "loss"
            else:
                updated_game["mentone_result"] = "draw"

    logger.info(f"Updated game result: {game_id}, Home: {home_score}, Away: {away_score}, Status: {updated_game['status']}")
    return updated_game

def update_game_in_firestore(db, game, dry_run=False):
    """Update a game in Firestore.

    Args:
        db: Firestore client
        game: Game dictionary with results
        dry_run: If True, don't write to database

    Returns:
        bool: Success status
    """
    if dry_run:
        return True

    try:
        # Use the game_id directly as the document ID
        game_id = game["id"]

        # Clean up references for Firestore
        # Don't overwrite existing references
        for ref_field in ["competition_ref", "grade_ref", "home_team_ref", "away_team_ref"]:
            if ref_field in game and "__ref__" in game[ref_field]:
                del game[ref_field]

        # Only update specific fields to preserve other data
        update_data = {
            "status": game["status"],
            "updated_at": game["updated_at"],
            "home_team": game["home_team"],
            "away_team": game["away_team"]
        }

        # Add mentone_result if available
        if "mentone_result" in game:
            update_data["mentone_result"] = game["mentone_result"]

        # Write to Firestore
        game_ref = db.collection("games").document(game_id)
        game_ref.update(update_data)
        return True

    except Exception as e:
        logger.error(f"Failed to update game (ID: {game.get('id', 'unknown')}): {str(e)}")
        return False

def find_games_to_update(db, days_back=DEFAULT_DAYS_BACK, game_id=None):
    """Find games that need result updates.

    Args:
        db: Firestore client
        days_back: Number of days back to look for games
        game_id: Optional specific game ID to update

    Returns:
        list: List of game dictionaries to update
    """
    games_to_update = []

    try:
        if game_id:
            # Get a specific game
            game_doc = db.collection("games").document(game_id).get()
            if game_doc.exists:
                game_data = game_doc.to_dict()
                game_data["id"] = game_doc.id
                games_to_update.append(game_data)
            else:
                logger.error(f"Game not found with ID: {game_id}")
        else:
            # Get games in date range that are scheduled or have no status
            # Only include games where Mentone is playing
            current_date = datetime.now()
            past_date = current_date - timedelta(days=days_back)

            # Get completed games first (to avoid updating already updated games)
            completed_games_query = db.collection("games") \
                .where("status", "==", "completed") \
                .where("date", ">=", past_date) \
                .where("date", "<=", current_date) \
                .where("mentone_playing", "==", True) \
                .stream()

            completed_game_ids = {game.id for game in completed_games_query}
            logger.debug(f"Found {len(completed_game_ids)} already completed games to skip")

            # Get scheduled games that should have already been played
            scheduled_games_query = db.collection("games") \
                .where("status", "==", "scheduled") \
                .where("date", ">=", past_date) \
                .where("date", "<=", current_date) \
                .where("mentone_playing", "==", True) \
                .stream()

            for game_doc in scheduled_games_query:
                if game_doc.id not in completed_game_ids:
                    game_data = game_doc.to_dict()
                    game_data["id"] = game_doc.id
                    games_to_update.append(game_data)

        logger.info(f"Found {len(games_to_update)} games to check for results")
        return games_to_update

    except Exception as e:
        logger.error(f"Error finding games to update: {e}")
        return []

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Update Hockey Victoria game results")

    parser.add_argument(
        "--game-id",
        type=str,
        help="Specific game ID to update (updates all recent Mentone games if not specified)"
    )

    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS_BACK,
        help=f"Number of days back to look for games to update (default: {DEFAULT_DAYS_BACK})"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without writing to database"
    )

    parser.add_argument(
        "--creds",
        type=str,
        help="Path to Firebase credentials file"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )

    args = parser.parse_args()

    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    global logger
    logger = setup_logger("update_results", log_level=log_level)

    try:
        # Initialize Firebase
        if not args.dry_run:
            logger.info("Initializing Firebase...")
            db = initialize_firebase(args.creds)
        else:
            logger.info("DRY RUN MODE - No database writes will be performed")
            db = None

        # Create a session for all requests
        import requests
        session = requests.Session()

        # Start update process
        start_time = datetime.now()

        # Find games to update
        games_to_update = find_games_to_update(db, args.days, args.game_id)

        # Update each game
        games_updated = 0
        games_unchanged = 0

        for game in games_to_update:
            logger.info(f"Processing game: {game.get('id')} - {game.get('home_team', {}).get('name', '')} vs {game.get('away_team', {}).get('name', '')}")

            # Update the game
            updated_game = update_game_result(logger, game, session)

            if not updated_game:
                logger.debug(f"No updates for game: {game.get('id')}")
                games_unchanged += 1
                continue

            # Save the updated game
            if not args.dry_run:
                success = update_game_in_firestore(db, updated_game)
                if success:
                    games_updated += 1
                    logger.info(f"Updated game result in database: {updated_game.get('id')}")
            else:
                games_updated += 1
                logger.info(f"[DRY RUN] Would update game result: {updated_game.get('id')}")

            # Sleep to avoid hammering the server
            time.sleep(DELAY_BETWEEN_REQUESTS)

        # Report results
        elapsed_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Results update completed in {elapsed_time:.2f} seconds.")
        logger.info(f"Updated {games_updated} games, {games_unchanged} games unchanged.")

        if args.dry_run:
            logger.info("DRY RUN - No database changes were made")

        return 0

    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        return 130
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())