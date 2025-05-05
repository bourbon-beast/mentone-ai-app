"""
Hockey Victoria Game Discovery Script

This script discovers games/fixtures for Mentone Hockey Club teams by:
1. Getting all Mentone teams from Firestore
2. Fetching the draw/schedule for each team from Hockey Victoria website
3. Parsing game details (date, venue, opponent, etc.)
4. Saving the game data to Firestore

Usage:
    python -m backend.scripts.discover_games [--team-id TEAM_ID] [--days DAYS] [--dry-run] [--creds CREDS_PATH] [--verbose]
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
from backend.utils.parsing_utils import clean_text, parse_date, extract_table_data, is_mentone_team

# Constants
BASE_URL = "https://www.hockeyvictoria.org.au"
DRAW_URL_TEMPLATE = "https://www.hockeyvictoria.org.au/games/{comp_id}/{fixture_id}"
GAME_URL_PATTERN = re.compile(r"/games/game/(\d+)")
DEFAULT_DAYS_AHEAD = 30  # days
MAX_ROUNDS_TO_CHECK = 23  # Maximum number of rounds to check, regardless of date

# Debug print
print("--- discover_games.py script starting ---")

def discover_games_for_team(logger, team, days_ahead=DEFAULT_DAYS_AHEAD, session=None, max_rounds=MAX_ROUNDS_TO_CHECK):
    """Discover upcoming games for a specific team by iterating through rounds.

    Args:
        logger: Logger instance
        team: Team dictionary containing comp_id and fixture_id
        days_ahead: Number of days ahead to look for games
        session: Optional requests session
        max_rounds: Maximum number of rounds to check

    Returns:
        list: List of game dictionaries
    """
    comp_id = team.get("comp_id")
    fixture_id = team.get("fixture_id")
    team_id = team.get("id")
    team_name = team.get("name")

    if not comp_id or not fixture_id:
        logger.error(f"Missing comp_id or fixture_id for team: {team_name}")
        return []

    # Base draw URL
    base_draw_url = DRAW_URL_TEMPLATE.format(comp_id=comp_id, fixture_id=fixture_id)
    logger.info(f"Discovering games for team: {team_name} from: {base_draw_url}")

    all_games = []
    current_date = datetime.now()
    end_date = current_date + timedelta(days=days_ahead)

    # Start at round 1 and increment until no more games are found
    round_num = 1
    empty_rounds_count = 0

    # Continue checking rounds until max_rounds (passed as parameter)
    while round_num <= max_rounds:
        # Construct the round-specific URL
        round_url = f"{base_draw_url}/round/{round_num}"
        logger.info(f"Checking round {round_num} at URL: {round_url}")

        response = make_request(round_url, session=session)

        # If page doesn't exist or returns error, assume we've reached the end of rounds
        if not response or response.status_code != 200:
            logger.info(f"No more rounds found after round {round_num-1}")
            break

        soup = BeautifulSoup(response.text, "html.parser")

        # Look for card-based game layouts
        game_cards = soup.select("div.card-body")

        if not game_cards:
            logger.warning(f"No game cards found for round {round_num}")
            empty_rounds_count += 1
            # Only stop after 3 consecutive empty rounds, to handle possible gaps in round publishing
            if empty_rounds_count >= 3:
                logger.info(f"Found {empty_rounds_count} consecutive empty rounds, stopping search.")
                break
            round_num += 1
            # Safe sleep to avoid hammering the server
            try:
                time.sleep(1.0)
            except Exception as e:
                logger.warning(f"Sleep error: {e}")
            continue

        # Reset empty rounds counter if we found cards
        empty_rounds_count = 0

        # Process each game card
        round_games = []
        games_found_count = 0

        for card in game_cards:
            try:
                # Initialize variables
                game_date = None
                venue = "TBD"
                venue_code = ""
                home_team_name = ""
                away_team_name = ""
                home_team_id = None
                away_team_id = None
                home_score = None
                away_score = None
                game_id = None
                game_url = None
                status = "scheduled"
                mentone_playing = False
                home_is_mentone = False
                away_is_mentone = False

                # Extract date and time
                date_time_div = card.select_one("div.col-md.pb-3.pb-lg-0.text-center.text-md-left")
                if not date_time_div:
                    logger.debug("No date/time div found in card, skipping")
                    continue

                # Get the raw HTML and replace <br> tags with a space
                date_time_html = str(date_time_div)
                date_time_html = date_time_html.replace('<br>', ' ').replace('<br/>', ' ')
                date_time_soup = BeautifulSoup(date_time_html, 'html.parser')
                date_time_text = clean_text(date_time_soup.get_text())

                # Find the date and time pattern in the text
                # This regex looks for day, date, month, year and time pattern
                date_time_pattern = r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})\s+(\d{1,2}:\d{2})'
                match = re.search(date_time_pattern, date_time_text)

                if match:
                    day, date, month, year, time = match.groups()
                    # Create a clean date string without any extra pitch info
                    clean_date_string = f"{day} {date} {month} {year} {time}"

                    try:
                        # Parse the clean date string
                        game_date = datetime.strptime(clean_date_string, "%a %d %b %Y %H:%M")
                        logger.debug(f"Successfully parsed date: {game_date}")
                    except ValueError as e:
                        logger.warning(f"Could not parse date from cleaned string: '{clean_date_string}' - {e}")
                        continue
                else:
                    logger.warning(f"Could not find date/time pattern in: '{date_time_text}'")
                    continue

                # Extract venue
                venue_div = card.select_one("div.col-md.pb-3.pb-lg-0.text-center.text-md-right.text-lg-left")
                if venue_div:
                    venue_link = venue_div.select_one("a")
                    if venue_link:
                        venue = clean_text(venue_link.text)

                    venue_code_elem = venue_div.select_one("div")
                    if venue_code_elem:
                        venue_code = clean_text(venue_code_elem.text)

                # Extract teams
                teams_div = card.select_one("div.col-lg-3.pb-3.pb-lg-0.text-center")
                if not teams_div:
                    logger.debug("No teams div found in card, skipping")
                    continue

                team_links = teams_div.select("a")
                if len(team_links) < 2:
                    logger.debug("Less than 2 team links found, skipping")
                    continue

                home_team_link = team_links[0]
                away_team_link = team_links[1]

                home_team_name = clean_text(home_team_link.text)
                away_team_name = clean_text(away_team_link.text)

                # Extract team IDs from links
                home_link_href = home_team_link.get("href", "")
                away_link_href = away_team_link.get("href", "")

                if "team" in home_link_href:
                    home_team_id = home_link_href.split("/")[-1]
                if "team" in away_link_href:
                    away_team_id = away_link_href.split("/")[-1]

                # Check if Mentone is playing
                home_is_mentone = is_mentone_team(home_team_name)
                away_is_mentone = is_mentone_team(away_team_name)
                mentone_playing = home_is_mentone or away_is_mentone

                # Skip if Mentone is not playing and we're only looking for Mentone games
                if not mentone_playing and team.get("is_home_club", False):
                    logger.debug(f"Mentone not playing in {home_team_name} vs {away_team_name}, skipping")
                    continue

                # Extract score if available
                score_div = teams_div.select_one("div b")
                if score_div:
                    score_text = clean_text(score_div.text)
                    score_parts = score_text.split('-')
                    if len(score_parts) == 2:
                        try:
                            home_score = int(score_parts[0].strip())
                            away_score = int(score_parts[1].strip())
                            status = "completed"  # If score exists, game is completed
                        except ValueError:
                            logger.warning(f"Could not parse score: {score_text}")

                # Extract game details link
                details_link = card.select_one("a.btn.btn-outline-primary.btn-sm")
                if details_link:
                    game_url = urljoin(BASE_URL, details_link.get("href", ""))
                    game_id = game_url.split("/")[-1]

                # If no game ID found, generate a unique ID
                if not game_id:
                    unique_str = f"{comp_id}_{fixture_id}_{game_date.strftime('%Y%m%d%H%M')}_{home_team_name}_{away_team_name}"
                    game_id = str(abs(hash(unique_str)) % (10 ** 10))

                # Create game dictionary
                game = {
                    "id": game_id,
                    "comp_id": comp_id,
                    "fixture_id": fixture_id,
                    "date": game_date,
                    "venue": venue,
                    "venue_code": venue_code,
                    "round": round_num,  # Use the explicit round number from the URL
                    "status": status,
                    "url": game_url,
                    "mentone_playing": mentone_playing,
                    "type": team.get("type"),
                    "updated_at": datetime.now(),
                    "created_at": datetime.now()
                }

                # Add home team info
                game["home_team"] = {
                    "id": home_team_id,
                    "name": home_team_name,
                    "club": home_team_name.split(" - ")[0].strip() if " - " in home_team_name else home_team_name,
                    "short_name": "Mentone" if home_is_mentone else home_team_name.replace(" Hockey Club", "").strip()
                }

                # Add score if available
                if home_score is not None:
                    game["home_team"]["score"] = home_score

                # Add away team info
                game["away_team"] = {
                    "id": away_team_id,
                    "name": away_team_name,
                    "club": away_team_name.split(" - ")[0].strip() if " - " in away_team_name else away_team_name,
                    "short_name": "Mentone" if away_is_mentone else away_team_name.replace(" Hockey Club", "").strip()
                }

                # Add score if available
                if away_score is not None:
                    game["away_team"]["score"] = away_score

                # Add references to teams and competition/grade
                if home_team_id:
                    game["home_team_ref"] = {"__ref__": f"teams/{home_team_id}"}
                if away_team_id:
                    game["away_team_ref"] = {"__ref__": f"teams/{away_team_id}"}

                game["competition_ref"] = {"__ref__": f"competitions/{comp_id}"}
                game["grade_ref"] = {"__ref__": f"grades/{fixture_id}"}

                round_games.append(game)
                games_found_count += 1
                logger.debug(f"Found game: {home_team_name} vs {away_team_name} on {game_date}")

            except Exception as e:
                logger.error(f"Error processing game card in round {round_num}: {e}")
                continue

        # If we found games in this round, add them to our overall list
        if round_games:
            logger.info(f"Found {len(round_games)} games in round {round_num}")
            all_games.extend(round_games)
        else:
            logger.info(f"No games found in round {round_num}")
            empty_rounds_count += 1
            if empty_rounds_count >= 3:  # If 3 consecutive empty rounds, assume we're done
                logger.info(f"Found {empty_rounds_count} consecutive empty rounds, stopping search.")
                break

        # Move to next round - continue until max_rounds
        round_num += 1

        # Safe sleep to avoid hammering the server
        try:
            time.sleep(1.0)
        except Exception as e:
            logger.warning(f"Sleep error: {e}")

    logger.info(f"Found {len(all_games)} games across all rounds for team: {team_name}")
    return all_games

def create_or_update_game(db, game, dry_run=False):
    """Create or update a game in Firestore.

    Args:
        db: Firestore client
        game: Game dictionary
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
        # Convert reference objects to Firestore references
        for ref_field in ["competition_ref", "grade_ref", "home_team_ref", "away_team_ref"]:
            if "__ref__" in game.get(ref_field, {}):
                ref_path = game[ref_field]["__ref__"]
                game[ref_field] = db.document(ref_path)

        # Convert date to Firestore timestamp
        if isinstance(game.get("date"), datetime):
            game["date"] = game["date"]

        # Write to Firestore
        game_ref = db.collection("games").document(game_id)
        game_ref.set(game, merge=True)
        return True

    except Exception as e:
        logger.error(f"Failed to save game (ID: {game.get('id', 'unknown')}): {str(e)}")
        return False

def find_existing_games(db, team_id, comp_id, fixture_id, start_date):
    """Find existing games in Firestore for deduplication.

    Args:
        db: Firestore client
        team_id: Team ID
        comp_id: Competition ID
        fixture_id: Fixture/Grade ID
        start_date: Start date for games

    Returns:
        dict: Dictionary of existing games keyed by a composite key
    """
    existing_games = {}

    try:
        # Query for games matching the team, competition, and grade
        games_query = db.collection("games") \
            .where("fixture_id", "==", fixture_id) \
            .where("date", ">=", start_date) \
            .stream()

        for game_doc in games_query:
            game_data = game_doc.to_dict()

            # Create a composite key for the game (date + teams)
            game_date = game_data.get("date")
            home_team = game_data.get("home_team", {}).get("name", "")
            away_team = game_data.get("away_team", {}).get("name", "")

            key = f"{game_date.strftime('%Y%m%d%H%M')}_{home_team}_{away_team}"

            existing_games[key] = {
                "id": game_doc.id,
                "date": game_date,
                "status": game_data.get("status")
            }

        logger.debug(f"Found {len(existing_games)} existing games for team ID: {team_id}")
        return existing_games

    except Exception as e:
        logger.error(f"Error finding existing games: {e}")
        return {}

def main():
    print("--- main() entered ---")
    # Define parser and arguments
    parser = argparse.ArgumentParser(
        description="Discover upcoming games for Mentone Hockey Club teams"
    )

    parser.add_argument(
        "--team-id",
        type=str,
        help="Specific team ID to process (default: all Mentone teams)"
    )

    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS_AHEAD,
        help=f"Number of days ahead to look for games (default: {DEFAULT_DAYS_AHEAD})"
    )

    parser.add_argument(
        "--max-rounds",
        type=int,
        default=MAX_ROUNDS_TO_CHECK,
        help=f"Maximum number of rounds to check (default: {MAX_ROUNDS_TO_CHECK})"
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
    print(f"--- Args parsed: {args} ---")

    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    global logger
    print("--- Setting up logger ---")
    logger = setup_logger("discover_games", log_level=log_level)
    print("--- Logger setup complete ---")
    logger.info("Logger initialized successfully.")

    try:
        print("--- Entering main try block ---")
        # Initialize Firebase
        if not args.dry_run:
            logger.info("Initializing Firebase...")
            db = initialize_firebase(args.creds)
        else:
            logger.info("DRY RUN MODE - No database writes will be performed")
            db = None  # Set to None in dry run mode

        print("--- Firebase initialized or skipped (dry run) ---")

        # Create a session for all requests
        import requests
        session = requests.Session()
        print("--- Request session created ---")

        # Get teams to process
        print("--- Attempting to get teams ---")
        teams = []  # Initialize
        if args.team_id:
            print(f"--- Specific team ID provided: {args.team_id} ---")
            if db:  # Check if db exists first
                # Get specific team by ID
                team_ref = db.collection("teams").document(args.team_id)
                team_doc = team_ref.get()
                if team_doc.exists:
                    teams = [{"id": team_doc.id, **team_doc.to_dict()}]
                else:
                    logger.error(f"Team with ID {args.team_id} not found")
            else:
                logger.warning("In dry run mode - cannot fetch team by ID without database")
                # Create mock data for testing if needed
        else:
            print("--- Getting all Mentone teams ---")
            # Only query if db exists
            if db:
                teams_query = db.collection("teams").where("is_home_club", "==", True).stream()
                teams = [{"id": doc.id, **doc.to_dict()} for doc in teams_query]
            else:
                # In dry run mode, teams list will be empty unless --team-id is used
                teams = []
                print("--- Dry run: Skipping Firestore query for teams ---")

        print(f"--- Found {len(teams)} teams to process ---")
        if not teams:
            logger.info("No teams found matching the criteria.")
            return 0

        # Process each team
        games_found = 0
        games_saved = 0

        for i, team in enumerate(teams):
            print(f"--- Processing team {i+1}/{len(teams)}: {team.get('name')} ---")

            # Discover games for the team (pass max_rounds if specified)
            team_games = discover_games_for_team(
                logger, team, days_ahead=args.days, session=session,
                max_rounds=args.max_rounds if args.max_rounds else MAX_ROUNDS_TO_CHECK
            )

            if not team_games:
                logger.info(f"No games found for team: {team.get('name')}")
                continue

            games_found += len(team_games)
            logger.info(f"Found {len(team_games)} games for team: {team.get('name')}")

            # Save games to Firestore
            if not args.dry_run and db:
                current_date = datetime.now()

                # Find existing games for deduplication
                existing_games = find_existing_games(
                    db, team.get("id"), team.get("comp_id"),
                    team.get("fixture_id"), current_date
                )

                for game in team_games:
                    # Create or update the game
                    saved = create_or_update_game(db, game, dry_run=args.dry_run)
                    if saved:
                        games_saved += 1

                    # Short delay to avoid hammering the database
                    try:
                        time.sleep(0.1)
                    except Exception as e:
                        logger.warning(f"Sleep error: {e}")
            else:
                # In dry run mode, just count the games
                games_saved = games_found

            # Short delay between teams
            try:
                time.sleep(1.0)
            except Exception as e:
                logger.warning(f"Sleep error: {e}")

        print("--- Finished processing loop ---")

        # Report results
        logger.info(f"Game discovery completed. Found {games_found} games, saved {games_saved} games.")
        if args.dry_run:
            logger.info("DRY RUN - No database changes were made")

        return 0

    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        return 130
    except Exception as e:
        # Ensure exceptions are printed if logger fails
        print(f"--- *** EXCEPTION CAUGHT: {e} *** ---")
        logger.error(f"Error: {e}", exc_info=True)
        return 1

    print("--- main() finished normally ---")
    return 0

if __name__ == "__main__":
    sys.exit(main())

# After the if __name__ == "__main__": block
print("--- discover_games.py script ending ---")