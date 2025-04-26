"""
Hockey Victoria Team Discovery Script

This script discovers teams for each competition/grade and identifies Mentone teams.
It extracts team information from the ladder pages and stores it in Firestore.

Usage:
    python -m backend.scripts.discover_teams [--comp-id COMP_ID] [--dry-run] [--creds CREDS_PATH] [--verbose]
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
from backend.utils.parsing_utils import clean_text, extract_table_data, is_mentone_team

# Constants
BASE_URL = "https://www.hockeyvictoria.org.au"
LADDER_URL_TEMPLATE = "https://www.hockeyvictoria.org.au/pointscore/{comp_id}/{fixture_id}"
TEAM_URL_PATTERN = re.compile(r"/games/team/(\d+)/(\d+)")
DELAY_BETWEEN_REQUESTS = 1  # seconds

def discover_teams_for_grade(logger, comp_id, fixture_id, grade_name, session=None):
    """Extract teams from the ladder page of a specific grade.

    Args:
        logger: Logger instance
        comp_id: Competition ID
        fixture_id: Fixture/Grade ID
        grade_name: Human-readable grade name
        session: Optional requests session

    Returns:
        list: List of team dictionaries
    """
    ladder_url = LADDER_URL_TEMPLATE.format(comp_id=comp_id, fixture_id=fixture_id)
    logger.info(f"Discovering teams for grade '{grade_name}' from: {ladder_url}")

    response = make_request(ladder_url, session=session)
    if not response:
        logger.error(f"Failed to get ladder page: {ladder_url}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    teams = []

    # Find the main ladder table
    table = soup.select_one("table.table")
    if not table:
        logger.error(f"No ladder table found at: {ladder_url}")
        return []

    # Parse team rows from the table
    rows = table.select("tbody tr")
    for row in rows:
        try:
            # Extract team position (rank)
            position_cell = row.select_one("td")
            if not position_cell:
                continue

            position_text = position_cell.text.strip()
            position_match = re.match(r"(\d+)\.", position_text)
            position = int(position_match.group(1)) if position_match else None

            # Extract team link and ID
            team_link = position_cell.select_one("a")
            if not team_link:
                continue

            team_name = clean_text(team_link.text)
            team_url = team_link.get("href", "")

            # Extract team ID from URL
            team_match = TEAM_URL_PATTERN.search(team_url)
            if not team_match:
                logger.warning(f"Could not extract team ID from URL: {team_url}")
                continue

            team_id = team_match.group(2)

            # Extract team stats from the row
            cells = row.select("td")
            if len(cells) < 10:  # Expect at least 10 columns in ladder table
                logger.warning(f"Incomplete team data row for: {team_name}")
                continue

            # Map column indices to their meaning
            played = int(cells[1].text.strip()) if cells[1].text.strip().isdigit() else 0
            wins = int(cells[2].text.strip()) if cells[2].text.strip().isdigit() else 0
            draws = int(cells[3].text.strip()) if cells[3].text.strip().isdigit() else 0
            losses = int(cells[4].text.strip()) if cells[4].text.strip().isdigit() else 0
            byes = int(cells[5].text.strip()) if cells[5].text.strip().isdigit() else 0
            goals_for = int(cells[6].text.strip()) if cells[6].text.strip().isdigit() else 0
            goals_against = int(cells[7].text.strip()) if cells[7].text.strip().isdigit() else 0
            goal_diff = int(cells[8].text.strip()) if cells[8].text.strip().replace('-', '').isdigit() else 0
            points = int(cells[9].text.strip()) if cells[9].text.strip().isdigit() else 0

            # Check if this is a Mentone team
            is_home_club = is_mentone_team(team_name)

            # Determine team gender based on grade name
            gender = determine_gender(grade_name)

            # Determine team type based on grade name
            team_type = determine_team_type(grade_name)

            # Create team dictionary
            team = {
                "id": team_id,
                "name": f"Mentone Hockey Club - {grade_name}" if is_home_club else team_name,
                "short_name": "Mentone" if is_home_club else team_name.replace(" Hockey Club", "").strip(),
                "club": "Mentone" if is_home_club else team_name.replace(" Hockey Club", "").strip(),
                "is_home_club": is_home_club,
                "url": urljoin(BASE_URL, team_url),
                "comp_id": int(comp_id),
                "fixture_id": int(fixture_id),
                "comp_name": grade_name,
                "ladder_position": position,
                "ladder_points": points,
                "ladder_updated_at": datetime.now(),
                "type": team_type,
                "gender": gender,
                "active": True,
                "stats": {
                    "games_played": played,
                    "wins": wins,
                    "draws": draws,
                    "losses": losses,
                    "byes": byes,
                    "goals_for": goals_for,
                    "goals_against": goals_against,
                    "goal_diff": goal_diff
                },
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }

            # Add competition reference (useful for Firestore queries)
            team["competition_ref"] = {"__ref__": f"competitions/{comp_id}"}
            team["grade_ref"] = {"__ref__": f"grades/{fixture_id}"}

            teams.append(team)
            logger.debug(f"Found team: {team_name} (ID: {team_id}, Position: {position})")

        except Exception as e:
            logger.error(f"Error processing team row: {e}")
            continue

    logger.info(f"Found {len(teams)} teams for grade '{grade_name}'")
    return teams

def determine_gender(grade_name):
    """Determine team gender from grade name.

    Args:
        grade_name: Grade name string

    Returns:
        str: Gender (Men, Women, Mixed, or Unknown)
    """
    grade_lower = grade_name.lower()

    if any(term in grade_lower for term in ["women's", "women", "female", "girls", "w'"]):
        return "Women"
    if any(term in grade_lower for term in ["men's", "men", "male", "boys", "m'"]):
        return "Men"
    if "mixed" in grade_lower:
        return "Mixed"

    return "Unknown"

def determine_team_type(grade_name):
    """Determine team type from grade name.

    Args:
        grade_name: Grade name string

    Returns:
        str: Team type (Senior, Junior, Midweek, etc.)
    """
    grade_lower = grade_name.lower()

    if any(term in grade_lower for term in ["junior", "under", "u1"]):
        return "Junior"
    if any(term in grade_lower for term in ["senior", "premier", "vic league", "pennant", "metro"]):
        return "Senior"
    if any(term in grade_lower for term in ["master", "veteran", "35+", "45+"]):
        return "Masters"
    if "midweek" in grade_lower:
        return "Midweek"
    if "indoor" in grade_lower:
        return "Indoor"

    # Default
    return "Senior"  # Assume senior if not specified

def create_or_update_team(db, team, dry_run=False):
    """Create or update a team in Firestore.

    Args:
        db: Firestore client
        team: Team dictionary
        dry_run: If True, don't write to database

    Returns:
        bool: Success status
    """
    if dry_run:
        return True

    try:
        # Use the team_id directly as the document ID
        team_id = team["id"]

        # Clean up references for Firestore
        # Convert reference objects to Firestore references
        if "__ref__" in team.get("competition_ref", {}):
            ref_path = team["competition_ref"]["__ref__"]
            team["competition_ref"] = db.document(ref_path)

        if "__ref__" in team.get("grade_ref", {}):
            ref_path = team["grade_ref"]["__ref__"]
            team["grade_ref"] = db.document(ref_path)

        # Write to Firestore
        team_ref = db.collection("teams").document(team_id)
        team_ref.set(team, merge=True)
        return True

    except Exception as e:
        logger.error(f"Failed to save team {team.get('name', 'unknown')} (ID: {team.get('id', 'unknown')}): {str(e)}")
        return False

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Discover Hockey Victoria teams")

    parser.add_argument(
        "--comp-id",
        type=str,
        help="Specific competition ID to process (processes all if not specified)"
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
    logger = setup_logger("discover_teams", log_level=log_level)

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

        # Get competitions/grades to process
        if args.comp_id:
            # Get specific competition/grades
            grades_query = db.collection("grades").where("comp_id", "==", int(args.comp_id)).stream()
            grades = [{
                "id": grade.id,
                "comp_id": grade.get("comp_id"),
                "name": grade.get("name")
            } for grade in grades_query]

            logger.info(f"Processing {len(list(grades))} grades for competition ID: {args.comp_id}")
        else:
            # Get all active grades
            grades_query = db.collection("grades").where("active", "==", True).stream()
            grades = [{
                "id": grade.id,
                "comp_id": grade.get("comp_id"),
                "name": grade.get("name")
            } for grade in grades_query]

            logger.info(f"Processing all {len(list(grades))} active grades")

        # Process each grade
        teams_found = 0
        mentone_teams_found = 0
        grades_processed = 0

        for grade in grades:
            grade_id = grade["id"]
            comp_id = grade["comp_id"]
            grade_name = grade["name"]

            logger.info(f"Processing grade: {grade_name} (ID: {grade_id})")

            # Discover teams for this grade
            teams = discover_teams_for_grade(logger, comp_id, grade_id, grade_name, session)

            # Process each team
            for team in teams:
                if not args.dry_run:
                    success = create_or_update_team(db, team)
                    if success:
                        teams_found += 1
                        if team["is_home_club"]:
                            mentone_teams_found += 1
                            logger.info(f"Saved Mentone team: {team['name']} (Position: {team['ladder_position']})")
                        else:
                            logger.debug(f"Saved team: {team['name']}")
                else:
                    teams_found += 1
                    if team["is_home_club"]:
                        mentone_teams_found += 1
                        logger.info(f"[DRY RUN] Would save Mentone team: {team['name']} (Position: {team['ladder_position']})")
                    else:
                        logger.debug(f"[DRY RUN] Would save team: {team['name']}")

            grades_processed += 1

            # Sleep to avoid hammering the server
            time.sleep(DELAY_BETWEEN_REQUESTS)

        # Report results
        elapsed_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Team discovery completed in {elapsed_time:.2f} seconds.")
        logger.info(f"Processed {grades_processed} grades, found {teams_found} teams ({mentone_teams_found} Mentone teams).")

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