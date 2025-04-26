"""
Hockey Victoria Ladder Update Script

This script updates ladder positions for Mentone Hockey Club teams by:
1. Fetching the latest ladder positions from Hockey Victoria website
2. Updating team documents in Firestore with position and points

Usage:
    python -m backend.scripts.update_ladder [--team-id TEAM_ID] [--dry-run] [--creds CREDS_PATH] [--verbose]
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
from backend.utils.parsing_utils import clean_text, extract_number

# Constants
BASE_URL = "https://www.hockeyvictoria.org.au"
LADDER_URL_TEMPLATE = "https://www.hockeyvictoria.org.au/pointscore/{comp_id}/{fixture_id}"
DELAY_BETWEEN_REQUESTS = 1  # seconds

def update_ladder_for_team(logger, team, session=None):
    """Update ladder position for a specific team.

    Args:
        logger: Logger instance
        team: Team dictionary containing comp_id, fixture_id, and name
        session: Optional requests session

    Returns:
        dict or None: Updated team data or None if no update
    """
    comp_id = team.get("comp_id")
    fixture_id = team.get("fixture_id")
    team_id = team.get("id")
    team_name = team.get("name")

    if not comp_id or not fixture_id:
        logger.error(f"Missing comp_id or fixture_id for team: {team_name}")
        return None

    ladder_url = LADDER_URL_TEMPLATE.format(comp_id=comp_id, fixture_id=fixture_id)
    logger.info(f"Getting ladder position for team: {team_name} from: {ladder_url}")

    response = make_request(ladder_url, session=session)
    if not response:
        logger.error(f"Failed to get ladder page: {ladder_url}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # Find the ladder table
    ladder_table = soup.select_one("table.table")
    if not ladder_table:
        logger.error(f"No ladder table found at: {ladder_url}")
        return None

    # Find Mentone in the table
    position = None
    points = None
    games_played = None
    wins = None
    draws = None
    losses = None
    goals_for = None
    goals_against = None
    goal_diff = None

    # Check table structure
    headers = [clean_text(th.text).lower() for th in ladder_table.select("thead th")]
    position_in_team_col = "team" in headers[0].lower()  # Position might be part of the team column

    # Find column indices for stats
    played_col = next((i for i, h in enumerate(headers) if "play" in h), None)
    wins_col = next((i for i, h in enumerate(headers) if "win" in h), None)
    draws_col = next((i for i, h in enumerate(headers) if "draw" in h), None)
    losses_col = next((i for i, h in enumerate(headers) if "loss" in h), None)
    for_col = next((i for i, h in enumerate(headers) if "for" in h), None)
    against_col = next((i for i, h in enumerate(headers) if "against" in h), None)
    diff_col = next((i for i, h in enumerate(headers) if "diff" in h), None)
    points_col = next((i for i, h in enumerate(headers) if "point" in h), None)

    # Process each row looking for Mentone
    rows = ladder_table.select("tbody tr")
    for row in rows:
        cells = row.select("td")
        if len(cells) == 0:
            continue

        # Check if this row contains Mentone
        team_cell = cells[0]
        team_cell_text = clean_text(team_cell.text).lower()

        # Extract position from the team cell if needed
        row_position = None
        if position_in_team_col:
            position_match = re.match(r'(\d+)\.', team_cell_text)
            if position_match:
                row_position = int(position_match.group(1))

        # Look for Mentone in this row
        if "mentone" in team_cell_text or team_id in team_cell_text:
            # Found Mentone, extract ladder data
            if row_position:
                position = row_position

            # Extract other stats
            if played_col is not None and len(cells) > played_col:
                games_played = extract_number(cells[played_col].text, None)

            if wins_col is not None and len(cells) > wins_col:
                wins = extract_number(cells[wins_col].text, None)

            if draws_col is not None and len(cells) > draws_col:
                draws = extract_number(cells[draws_col].text, None)

            if losses_col is not None and len(cells) > losses_col:
                losses = extract_number(cells[losses_col].text, None)

            if for_col is not None and len(cells) > for_col:
                goals_for = extract_number(cells[for_col].text, None)

            if against_col is not None and len(cells) > against_col:
                goals_against = extract_number(cells[against_col].text, None)

            if diff_col is not None and len(cells) > diff_col:
                goal_diff = extract_number(cells[diff_col].text, None)

            if points_col is not None and len(cells) > points_col:
                points = extract_number(cells[points_col].text, None)

            # If no position was found in team cell, use row index + 1
            if position is None:
                position = rows.index(row) + 1

            break

    # If no position found, team may not be in this competition
    if position is None:
        logger.warning(f"Team {team_name} not found in ladder at: {ladder_url}")
        return None

    # Create updated team data
    updated_team = {
        "id": team_id,
        "ladder_position": position,
        "ladder_points": points,
        "ladder_updated_at": datetime.now()
    }

    # Add additional stats if available
    ladder_stats = {}
    if games_played is not None:
        ladder_stats["games_played"] = games_played
    if wins is not None:
        ladder_stats["wins"] = wins
    if draws is not None:
        ladder_stats["draws"] = draws
    if losses is not None:
        ladder_stats["losses"] = losses
    if goals_for is not None:
        ladder_stats["goals_for"] = goals_for
    if goals_against is not None:
        ladder_stats["goals_against"] = goals_against
    if goal_diff is not None:
        ladder_stats["goal_diff"] = goal_diff

    if ladder_stats:
        updated_team["ladder_stats"] = ladder_stats

    logger.info(f"Updated ladder position for {team_name}: Position {position}, Points {points}")
    return updated_team

def update_team_in_firestore(db, team_data, dry_run=False):
    """Update a team in Firestore with ladder position.

    Args:
        db: Firestore client
        team_data: Team data with ladder position
        dry_run: If True, don't write to database

    Returns:
        bool: Success status
    """
    if dry_run:
        return True

    try:
        # Use the team_id as the document ID
        team_id = team_data["id"]

        # Only update specific fields
        update_data = {
            "ladder_position": team_data["ladder_position"],
            "ladder_updated_at": team_data["ladder_updated_at"]
        }

        # Add points if available
        if "ladder_points" in team_data:
            update_data["ladder_points"] = team_data["ladder_points"]

        # Add ladder stats if available
        if "ladder_stats" in team_data:
            update_data["ladder_stats"] = team_data["ladder_stats"]

        # Update the team document
        team_ref = db.collection("teams").document(team_id)
        team_ref.update(update_data)
        return True

    except Exception as e:
        logger.error(f"Failed to update team (ID: {team_data.get('id', 'unknown')}): {str(e)}")
        return False

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Update Hockey Victoria ladder positions")

    parser.add_argument(
        "--team-id",
        type=str,
        help="Specific team ID to update (updates all Mentone teams if not specified)"
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
    logger = setup_logger("update_ladder", log_level=log_level)

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

        # Get teams to update
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
                "name": team_doc.get("name")
            }]

            logger.info(f"Updating ladder position for team: {teams[0]['name']}")
        else:
            # Get all Mentone teams
            teams_query = db.collection("teams").where("is_home_club", "==", True).stream()
            teams = [{
                "id": team.id,
                "comp_id": team.get("comp_id"),
                "fixture_id": team.get("fixture_id"),
                "name": team.get("name")
            } for team in teams_query if team.get("comp_id") and team.get("fixture_id")]

            logger.info(f"Updating ladder positions for {len(list(teams))} Mentone teams")

        # Process each team
        teams_updated = 0
        teams_processed = 0

        for team in teams:
            team_id = team["id"]
            team_name = team["name"]

            logger.info(f"Processing ladder for team: {team_name} (ID: {team_id})")

            # Update ladder position
            updated_team = update_ladder_for_team(logger, team, session)

            if not updated_team:
                logger.warning(f"No ladder update for team: {team_id}")
                teams_processed += 1
                continue

            # Save the updated team
            if not args.dry_run:
                success = update_team_in_firestore(db, updated_team)
                if success:
                    teams_updated += 1
                    logger.info(f"Updated ladder position in database: {team_name}")
            else:
                teams_updated += 1
                logger.info(f"[DRY RUN] Would update ladder position: {team_name}")

            teams_processed += 1

            # Sleep to avoid hammering the server
            time.sleep(DELAY_BETWEEN_REQUESTS)

        # Report results
        elapsed_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Ladder update completed in {elapsed_time:.2f} seconds.")
        logger.info(f"Processed {teams_processed} teams, updated {teams_updated} teams.")

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