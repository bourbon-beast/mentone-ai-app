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
DELAY_BETWEEN_REQUESTS = 1  # seconds
DEFAULT_DAYS_AHEAD = 14  # days


def discover_games_for_team(logger, team, days_ahead=DEFAULT_DAYS_AHEAD, session=None):
    """Discover upcoming games for a specific team.

    Args:
        logger: Logger instance
        team: Team dictionary containing comp_id and fixture_id
        days_ahead: Number of days ahead to look for games
        session: Optional requests session

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

    draw_url = DRAW_URL_TEMPLATE.format(comp_id=comp_id, fixture_id=fixture_id)
    logger.info(f"Discovering games for team: {team_name} from: {draw_url}")

    response = make_request(draw_url, session=session)
    if not response:
        logger.error(f"Failed to get draw page: {draw_url}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    games = []
    current_date = datetime.now()
    end_date = current_date + timedelta(days=days_ahead)

    # Find the games table(s)
    game_tables = soup.select("table.table")
    if not game_tables:
        logger.error(f"No game tables found at: {draw_url}")
        return []

    # Process each table (they might be organized by round)
    for table in game_tables:
        # Check if this is a games table by looking for header
        headers = [clean_text(th.text).lower() for th in table.select("thead th")]
        if not any(header in ["date", "time", "home", "away", "venue"] for header in headers):
            continue  # Not a games table

        # Determine column indices based on headers
        date_col = next((i for i, h in enumerate(headers) if "date" in h), None)
        time_col = next((i for i, h in enumerate(headers) if "time" in h), None)
        home_col = next((i for i, h in enumerate(headers) if "home" in h), None)
        away_col = next((i for i, h in enumerate(headers) if "away" in h), None)
        venue_col = next((i for i, h in enumerate(headers) if "venue" in h), None)
        round_col = next((i for i, h in enumerate(headers) if "round" in h), None)

        # Check if we have all necessary columns
        if None in [date_col, home_col, away_col]:
            logger.warning(f"Missing essential columns in game table")
            continue

        # Find current round from page heading if available
        current_round = None
        round_headings = soup.select("h1, h2, h3, h4")
        for heading in round_headings:
            round_match = re.search(r"round\s+(\d+)", heading.text.lower())
            if round_match:
                current_round = int(round_match.group(1))
                break

        # Parse game rows
        rows = table.select("tbody tr")
        for row in rows:
            try:
                cells = row.select("td")
                if len(cells) <= max(date_col, home_col, away_col):
                    continue  # Not enough cells

                # Extract date and time
                date_text = clean_text(cells[date_col].text)
                time_text = clean_text(cells[time_col].text) if time_col is not None else None

                # Parse date
                game_date = None
                if date_text:
                    # Try common formats
                    formats = [
                        '%a %d %b %Y',  # Mon 25 Dec 2023
                        '%a %d %b',     # Mon 25 Dec (current year)
                        '%d/%m/%Y',     # 25/12/2023
                        '%d/%m',        # 25/12 (current year)
                    ]

                    for fmt in formats:
                        try:
                            if '%Y' not in fmt:  # Add current year if not in format
                                date_text += f" {current_date.year}"
                                fmt += " %Y"

                            game_date = datetime.strptime(date_text, fmt)
                            break
                        except ValueError:
                            continue

                if not game_date:
                    logger.warning(f"Could not parse date: {date_text}")
                    continue

                # Add time if available
                if time_text and ":" in time_text:
                    hour, minute = map(int, time_text.split(':'))
                    game_date = game_date.replace(hour=hour, minute=minute)

                # Skip games outside our date range
                if game_date < current_date or game_date > end_date:
                    continue

                # Extract teams
                home_cell = cells[home_col]
                away_cell = cells[away_col]

                home_team_name = clean_text(home_cell.text)
                away_team_name = clean_text(away_cell.text)

                # Extract the home and away team IDs if available
                home_team_id = None
                away_team_id = None

                home_link = home_cell.select_one("a")
                if home_link and "team" in home_link.get("href", ""):
                    home_team_id = home_link.get("href", "").split("/")[-1]

                away_link = away_cell.select_one("a")
                if away_link and "team" in away_link.get("href", ""):
                    away_team_id = away_link.get("href", "").split("/")[-1]

                # Check if Mentone is playing
                home_is_mentone = is_mentone_team(home_team_name)
                away_is_mentone = is_mentone_team(away_team_name)
                mentone_playing = home_is_mentone or away_is_mentone

                # Skip if Mentone is not playing and we're only looking for Mentone games
                if not mentone_playing and team.get("is_home_club", False):
                    continue

                # Extract venue
                venue = clean_text(cells[venue_col].text) if venue_col is not None else "TBD"

                # Extract round number
                round_num = None
                if round_col is not None:
                    round_text = clean_text(cells[round_col].text)
                    round_match = re.search(r"(\d+)", round_text)
                    if round_match:
                        round_num = int(round_match.group(1))

                # Use current round from page if available and not found in row
                if round_num is None and current_round is not None:
                    round_num = current_round

                # Extract game ID if available (often in a link to the game details)
                game_id = None
                game_link = row.select_one(f"a[href*='/games/game/']")
                if game_link:
                    game_url = game_link.get("href", "")
                    game_match = GAME_URL_PATTERN.search(game_url)
                    if game_match:
                        game_id = game_match.group(1)

                # If no game ID found, generate a unique ID
                if not game_id:
                    unique_str = f"{comp_id}_{fixture_id}_{game_date.strftime('%Y%m%d%H%M')}_{home_team_name}_{away_team_name}"
                    # Create a reproducible hash as ID
                    game_id = str(abs(hash(unique_str)) % (10 ** 10))

                # Create game dictionary
                game = {
                    "id": game_id,
                    "comp_id": comp_id,
                    "fixture_id": fixture_id,
                    "date": game_date,
                    "venue": venue,
                    "round": round_num,
                    "status": "scheduled",  # Default status
                    "url": urljoin(BASE_URL, game_link.get("href", "")) if game_link else None,
                    "mentone_playing": mentone_playing,
                    "type": team.get("type"),  # Copy type from team (Senior, Junior, etc.)
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

                # Add away team info
                game["away_team"] = {
                    "id": away_team_id,
                    "name": away_team_name,
                    "club": away_team_name.split(" - ")[0].strip() if " - " in away_team_name else away_team_name,
                    "short_name": "Mentone" if away_is_mentone else away_team_name.replace(" Hockey Club", "").strip()
                }

                # Add references to teams and competition/grade
                if home_team_id:
                    game["home_team_ref"] = {"__ref__": f"teams/{home_team_id}"}
                if away_team_id:
                    game["away_team_ref"] = {"__ref__": f"teams/{away_team_id}"}

                game["competition_ref"] = {"__ref__": f"competitions/{comp_id}"}
                game["grade_ref"] = {"__ref__": f"grades/{fixture_id}"}

                games.append(game)
                logger.debug(f"Found game: {home_team_name} vs {away_team_name} on {game_date}")

            except Exception as e:
                logger.error(f"Error processing game row: {e}")
                continue

    logger.info(f"Found {len(games)} games for team: {team_name}")
    return games

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
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Discover Hockey Victoria games")

    parser.add_argument(
        "--team-id",
        type=str,
        help="Specific team ID to process (processes all Mentone teams if not specified)"
    )

    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS_AHEAD,
        help=f"Number of days ahead to look for games (default: {DEFAULT_DAYS_AHEAD})"
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
    logger = setup_logger("discover_games", log_level=log_level)

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

        # Start discovery process
        start_time = datetime.now()
        current_date = datetime.now()

        # Get teams to process
        if args.team_id:
            # Get specific team
            team_doc = db.collection("teams").document(args.team_id).get()
            if not team_doc.exists:
                logger.error(f"Team not found with ID: {args.team_id}")
                return 1

            teams = [{
                "id": team_doc.id,
                "comp_id": team_doc.get("comp_id"),
                "fixture_id": team_doc.get("fixture_id"),
                "name": team_doc.get("name"),
                "is_home_club": team_doc.get("is_home_club", False),
                "type": team_doc.get("type")
            }]

            logger.info(f"Processing games for team: {teams[0]['name']}")
        else:
            # Get all Mentone teams
            teams_query = db.collection("teams").where("is_home_club", "==", True).stream()
            teams = [{
                "id": team.id,
                "comp_id": team.get("comp_id"),
                "fixture_id": team.get("fixture_id"),
                "name": team.get("name"),
                "is_home_club": True,
                "type": team.get("type")
            } for team in teams_query]

            logger.info(f"Processing games for {len(list(teams))} Mentone teams")

        # Process each team
        games_found = 0
        mentone_games_found = 0
        teams_processed = 0

        for team in teams:
            team_id = team["id"]
            comp_id = team["comp_id"]
            fixture_id = team["fixture_id"]

            logger.info(f"Processing games for team: {team['name']} (ID: {team_id})")

            # Find existing games to avoid duplicates
            existing_games = find_existing_games(db, team_id, comp_id, fixture_id, current_date)

            # Discover games for this team
            games = discover_games_for_team(logger, team, args.days, session)

            # Process each game
            for game in games:
                # Check if game already exists in the database
                game_date = game.get("date")
                home_team = game.get("home_team", {}).get("name", "")
                away_team = game.get("away_team", {}).get("name", "")

                key = f"{game_date.strftime('%Y%m%d%H%M')}_{home_team}_{away_team}"

                if key in existing_games:
                    existing_game = existing_games[key]

                    # Update game ID to match existing record
                    game["id"] = existing_game["id"]

                    # Keep existing status if it's already completed
                    if existing_game.get("status") == "completed":
                        game["status"] = "completed"

                    logger.debug(f"Updating existing game: {home_team} vs {away_team} on {game_date}")
                else:
                    logger.debug(f"New game: {home_team} vs {away_team} on {game_date}")

                # Save game to the database
                if not args.dry_run:
                    success = create_or_update_game(db, game)
                    if success:
                        games_found += 1
                        if game["mentone_playing"]:
                            mentone_games_found += 1
                            logger.info(f"Saved Mentone game: {home_team} vs {away_team} on {game_date}")
                        else:
                            logger.debug(f"Saved game: {home_team} vs {away_team}")
                else:
                    games_found += 1
                    if game["mentone_playing"]:
                        mentone_games_found += 1
                        logger.info(f"[DRY RUN] Would save Mentone game: {home_team} vs {away_team} on {game_date}")
                    else:
                        logger.debug(f"[DRY RUN] Would save game: {home_team} vs {away_team}")

            teams_processed += 1

            # Sleep to avoid hammering the server
            time.sleep(DELAY_BETWEEN_REQUESTS)

        # Report results
        elapsed_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Game discovery completed in {elapsed_time:.2f} seconds.")
        logger.info(f"Processed {teams_processed} teams, found {games_found} games ({mentone_games_found} Mentone games).")

        if args.dry_run:
            logger.info("DRY RUN - No database changes were made")

        return 0

    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        return 130
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1