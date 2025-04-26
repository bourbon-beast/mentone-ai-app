"""
Hockey Victoria Player Discovery Script

This script discovers player data for Mentone Hockey Club by:
1. Getting player statistics from team pages on Hockey Victoria website
2. Processing player data and extracting statistics
3. Saving the player data to Firestore

Usage:
    python -m backend.scripts.discover_players [--team-id TEAM_ID] [--dry-run] [--creds CREDS_PATH] [--verbose]
"""

import argparse
import sys
import re
import time
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# Import utility modules
from backend.utils.firebase_init import initialize_firebase
from backend.utils.request_utils import make_request, build_url
from backend.utils.logging_utils import setup_logger
from backend.utils.parsing_utils import clean_text, extract_number, extract_table_data

# Constants
BASE_URL = "https://www.hockeyvictoria.org.au"
TEAM_STATS_URL_TEMPLATE = "https://www.hockeyvictoria.org.au/games/team-stats/{comp_id}?team={team_id}"
PLAYER_URL_PATTERN = re.compile(r"/games/player/(\d+)")
DELAY_BETWEEN_REQUESTS = 1  # seconds

def discover_players_for_team(logger, team, session=None):
    """Discover players for a specific team.

    Args:
        logger: Logger instance
        team: Team dictionary containing comp_id and id
        session: Optional requests session

    Returns:
        list: List of player dictionaries
    """
    comp_id = team.get("comp_id")
    team_id = team.get("id")
    team_name = team.get("name")

    if not comp_id or not team_id:
        logger.error(f"Missing comp_id or team_id for team: {team_name}")
        return []

    stats_url = TEAM_STATS_URL_TEMPLATE.format(comp_id=comp_id, team_id=team_id)
    logger.info(f"Discovering players for team: {team_name} from: {stats_url}")

    response = make_request(stats_url, session=session)
    if not response:
        logger.error(f"Failed to get team stats page: {stats_url}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    players = []

    # Find player statistics tables
    player_tables = soup.select("table.table")
    if not player_tables:
        logger.error(f"No player statistics tables found at: {stats_url}")
        return []

    # Process each table (field players, goalkeepers, etc.)
    for table_idx, table in enumerate(player_tables):
        # Check if this is a players table by looking for header
        headers = [clean_text(th.text).lower() for th in table.select("thead th")]

        # Skip tables without player data
        if not any(header in ["player", "name", "matches", "goals"] for header in headers):
            continue

        # Determine column indices based on headers
        player_col = next((i for i, h in enumerate(headers) if "player" in h or "name" in h), None)
        matches_col = next((i for i, h in enumerate(headers) if "matches" in h or "games" in h), None)
        goals_col = next((i for i, h in enumerate(headers) if "goals" in h), None)
        assists_col = next((i for i, h in enumerate(headers) if "assists" in h), None)
        green_cards_col = next((i for i, h in enumerate(headers) if "green" in h), None)
        yellow_cards_col = next((i for i, h in enumerate(headers) if "yellow" in h), None)
        red_cards_col = next((i for i, h in enumerate(headers) if "red" in h), None)

        # Check if we have essential columns
        if player_col is None:
            logger.warning(f"Missing player column in table {table_idx+1}")
            continue

        # Determine player type from table headers or structure
        player_type = "field"  # Default
        for header in headers:
            if "keeper" in header or "goalie" in header:
                player_type = "goalkeeper"
                break

        # Parse player rows
        rows = table.select("tbody tr")
        for row_idx, row in enumerate(rows):
            try:
                cells = row.select("td")
                if len(cells) <= player_col:
                    continue  # Not enough cells

                # Extract player name and ID
                player_cell = cells[player_col]
                player_name = clean_text(player_cell.text)

                # Skip empty or placeholder rows
                if not player_name or player_name.lower() in ["total", "team total"]:
                    continue

                # Extract player ID from link
                player_id = None
                player_link = player_cell.select_one("a")
                if player_link:
                    player_url = player_link.get("href", "")
                    player_match = PLAYER_URL_PATTERN.search(player_url)
                    if player_match:
                        player_id = player_match.group(1)

                # If no ID, generate a consistent one based on name and team
                if not player_id:
                    player_id = f"player_{team_id}_{re.sub(r'[^a-z0-9]', '', player_name.lower())}"

                # Extract statistics
                games_played = extract_number(cells[matches_col].text, 0) if matches_col is not None and len(cells) > matches_col else 0
                goals = extract_number(cells[goals_col].text, 0) if goals_col is not None and len(cells) > goals_col else 0
                assists = extract_number(cells[assists_col].text, 0) if assists_col is not None and len(cells) > assists_col else 0
                green_cards = extract_number(cells[green_cards_col].text, 0) if green_cards_col is not None and len(cells) > green_cards_col else 0
                yellow_cards = extract_number(cells[yellow_cards_col].text, 0) if yellow_cards_col is not None and len(cells) > yellow_cards_col else 0
                red_cards = extract_number(cells[red_cards_col].text, 0) if red_cards_col is not None and len(cells) > red_cards_col else 0

                # Create player dictionary
                player = {
                    "id": player_id,
                    "name": player_name,
                    "team_id": team_id,
                    "primary_team_id": team_id,  # Default primary team
                    "primary_team_name": team_name,
                    "type": player_type,
                    "gender": team.get("gender", "Unknown"),
                    "is_mentone_player": True,  # Assume all players on Mentone team are Mentone players
                    "active": True,
                    "stats": {
                        "games_played": games_played,
                        "goals": goals,
                        "assists": assists,
                        "green_cards": green_cards,
                        "yellow_cards": yellow_cards,
                        "red_cards": red_cards,
                    },
                    "updated_at": datetime.now(),
                    "created_at": datetime.now()
                }

                # Add team reference
                player["team_ref"] = {"__ref__": f"teams/{team_id}"}
                player["primary_team_ref"] = {"__ref__": f"teams/{team_id}"}

                players.append(player)
                logger.debug(f"Found player: {player_name} (ID: {player_id}, Games: {games_played}, Goals: {goals})")

            except Exception as e:
                logger.error(f"Error processing player row {row_idx+1}: {e}")
                continue

    logger.info(f"Found {len(players)} players for team: {team_name}")
    return players


def create_or_update_player(db, player, dry_run=False):
    """Create or update a player in Firestore.

    Args:
        db: Firestore client
        player: Player dictionary
        dry_run: If True, don't write to database

    Returns:
        bool: Success status
    """
    if dry_run:
        return True

    try:
        # Use the player_id as the document ID
        player_id = player["id"]

        # Clean up references for Firestore
        # Convert reference objects to Firestore references
        if "__ref__" in player.get("team_ref", {}):
            ref_path = player["team_ref"]["__ref__"]
            player["team_ref"] = db.document(ref_path)

        if "__ref__" in player.get("primary_team_ref", {}):
            ref_path = player["primary_team_ref"]["__ref__"]
            player["primary_team_ref"] = db.document(ref_path)

        # Check if player already exists
        player_ref = db.collection("players").document(player_id)
        player_doc = player_ref.get()

        if player_doc.exists:
            # Update existing player
            existing_data = player_doc.to_dict()

            # Update stats (add to existing rather than replace)
            if "stats" in existing_data and "stats" in player:
                existing_stats = existing_data["stats"]
                new_stats = player["stats"]

                # If the existing data is more recent, keep it
                if existing_data.get("updated_at", datetime(1970, 1, 1)) > player.get("updated_at", datetime.now()):
                    logger.debug(f"Existing player data is more recent, skipping stats update for: {player['name']}")
                else:
                    # Otherwise update with new stats (but don't overwrite with zeros if existing has values)
                    for stat_key, stat_value in new_stats.items():
                        if stat_value > 0 or stat_key not in existing_stats:
                            existing_stats[stat_key] = stat_value

                player["stats"] = existing_stats

                # Don't overwrite existing created_at
                player["created_at"] = existing_data.get("created_at", player["created_at"])

                # Merge teams - if player exists in multiple teams
                if existing_data.get("team_id") != player.get("team_id"):
                    # Add to teams list if not already there
                    teams = existing_data.get("teams", [])
                    new_team = {"id": player["team_id"], "name": player["primary_team_name"]}

                    if not any(t.get("id") == new_team["id"] for t in teams):
                        teams.append(new_team)
                        player["teams"] = teams

            # Update the document with merge
            player_ref.set(player, merge=True)
            return True
        else:
            # Create new player
            # Initialize teams list
            player["teams"] = [{"id": player["team_id"], "name": player["primary_team_name"]}]

            # Write to Firestore
            player_ref.set(player)
            return True

    except Exception as e:
        logger.error(f"Failed to save player {player.get('name', 'unknown')} (ID: {player.get('id', 'unknown')}): {str(e)}")
        return False


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Discover Hockey Victoria players")

    parser.add_argument(
        "--team-id",
        type=str,
        help="Specific team ID to process (processes all Mentone teams if not specified)"
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
    logger = setup_logger("discover_players", log_level=log_level)

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
                "name": team_doc.get("name"),
                "gender": team_doc.get("gender"),
                "is_home_club": team_doc.get("is_home_club", False)
            }]

            logger.info(f"Processing players for team: {teams[0]['name']}")
        else:
            # Get all Mentone teams
            teams_query = db.collection("teams").where("is_home_club", "==", True).stream()
            teams = [{
                "id": team.id,
                "comp_id": team.get("comp_id"),
                "name": team.get("name"),
                "gender": team.get("gender"),
                "is_home_club": True
            } for team in teams_query]

            logger.info(f"Processing players for {len(list(teams))} Mentone teams")

        # Process each team
        players_found = 0
        teams_processed = 0

        for team in teams:
            team_id = team["id"]
            team_name = team["name"]

            logger.info(f"Processing players for team: {team_name} (ID: {team_id})")

            # Discover players for this team
            players = discover_players_for_team(logger, team, session)

            # Process each player
            for player in players:
                if not args.dry_run:
                    success = create_or_update_player(db, player)
                    if success:
                        players_found += 1
                        logger.debug(f"Saved player: {player['name']}")
                else:
                    players_found += 1
                    logger.debug(f"[DRY RUN] Would save player: {player['name']}")

            teams_processed += 1

            # Sleep to avoid hammering the server
            time.sleep(DELAY_BETWEEN_REQUESTS)

        # Report results
        elapsed_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Player discovery completed in {elapsed_time:.2f} seconds.")
        logger.info(f"Processed {teams_processed} teams, found {players_found} players.")

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