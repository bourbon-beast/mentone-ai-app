"""
Hockey Victoria Competition Discovery Script

This script scrapes the Hockey Victoria website to discover competitions 
and their corresponding grades, storing the data in Firebase Firestore.
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
from backend.utils.parsing_utils import clean_text, save_debug_html, extract_table_data

# Constants
BASE_URL = "https://www.hockeyvictoria.org.au"
COMPETITIONS_URL = urljoin(BASE_URL, "/games/")
COMP_FIXTURE_REGEX = re.compile(r"/games/(\d+)/(\d+)")
CURRENT_YEAR = datetime.now().year




def sanitize_for_firestore(data):
    """Clean and validate data for Firestore compatibility.

    Args:
        data: Dictionary to clean

    Returns:
        dict: Cleaned dictionary
    """
    if not isinstance(data, dict):
        return data

    clean_data = {}

    for key, value in data.items():
        # Skip empty values
        if value is None:
            continue

        # Handle nested dictionaries
        if isinstance(value, dict):
            clean_data[key] = sanitize_for_firestore(value)
        # Handle lists
        elif isinstance(value, list):
            clean_data[key] = [sanitize_for_firestore(item) if isinstance(item, dict) else item for item in value]
        # Handle basic types
        elif isinstance(value, (str, int, float, bool, datetime)):
            clean_data[key] = value
        # Convert anything else to string
        else:
            try:
                clean_data[key] = str(value)
                logger.warning(f"Converted {key} of type {type(value)} to string")
            except:
                logger.warning(f"Skipped field {key} with unconvertible type {type(value)}")

    return clean_data#!/usr/bin/env python



def discover_competition_links(logger, session=None):
    """
    Scrape the main competitions page to find all competitions and grades.

    Args:
        logger: Logger instance
        session: Optional requests session

    Returns:
        tuple: (competitions dict, grades list) - properly associated
    """
    logger.info(f"Discovering competitions from: {COMPETITIONS_URL}")
    response = make_request(COMPETITIONS_URL, session=session)

    if not response:
        logger.error(f"Failed to get competitions page: {COMPETITIONS_URL}")
        return {}, []

    soup = BeautifulSoup(response.text, "html.parser")

    # For debugging
    # save_debug_html(response.text, "competitions_page")

    competitions = {}  # Dictionary keyed by comp_id
    grades = []        # List of grades
    current_comp_id = None
    current_comp_name = None

    # Find competition headings and their associated grades
    for element in soup.select("div.p-4, div.px-4.py-2.border-top"):
        # Check if this is a competition heading container
        heading = element.select_one("h2.h4")
        if heading:
            current_comp_name = clean_text(heading.text)
            # Extract comp_id if available in download link
            download_link = element.select_one("a[href*='/reports/games/']")
            if download_link:
                href = download_link.get("href", "")
                comp_id_match = re.search(r'/reports/games/(\d+)', href)
                if comp_id_match:
                    current_comp_id = comp_id_match.group(1)
                    logger.debug(f"Found competition heading: {current_comp_name} [ID: {current_comp_id}]")

                    # Create competition entry
                    competitions[current_comp_id] = {
                        "id": current_comp_id,
                        "name": current_comp_name,
                        "url": urljoin(BASE_URL, href),
                        "active": True,
                        "created_at": datetime.now(),
                        "updated_at": datetime.now(),
                    }
            continue

        # Extract grade links
        links = element.select("a")
        for link in links:
            href = link.get("href", "")
            match = COMP_FIXTURE_REGEX.search(href)

            if match:
                comp_id, fixture_id = match.groups()
                grade_name = clean_text(link.text)

                logger.debug(f"Found grade: {grade_name} [Comp ID: {comp_id}, Fixture ID: {fixture_id}]")

                # Create grade entry with reference to parent competition
                grade = {
                    "id": fixture_id,
                    "fixture_id": int(fixture_id),  # Store as integer
                    "comp_id": int(comp_id),        # Store as integer
                    "name": grade_name,
                    "url": urljoin(BASE_URL, href),
                    "active": True,
                    "created_at": datetime.now(),
                    "updated_at": datetime.now(),
                    "last_checked": datetime.now(),
                    "parent_comp_id": current_comp_id,  # Link to parent competition
                    "parent_comp_name": current_comp_name  # Store parent name for reference
                }

                grades.append(grade)

    logger.info(f"Found {len(competitions)} competitions and {len(grades)} grades")
    return competitions, grades


def get_competition_details(logger, competition, session=None):
    """Fetch additional details for a competition.

    Args:
        logger: Logger instance
        competition: Competition dictionary with basic info
        session: Optional requests session

    Returns:
        dict: Updated competition dictionary with additional details
    """
    # Extract season year from name first
    competition["season"] = str(extract_season_year(competition["name"], None))

    # Determine competition type
    competition["type"] = determine_competition_type(competition["category"], competition["name"])

    # Set needed values to match your data structure
    competition["start_date"] = competition["created_at"]

    return competition

def get_grade_details(logger, grade, session=None):
    """Fetch additional details for a grade by visiting its page.

    Args:
        logger: Logger instance
        grade: Grade dictionary with basic info
        session: Optional requests session

    Returns:
        dict: Updated grade dictionary with additional details
    """
    grade_url = grade["url"]
    logger.info(f"Getting details for grade: {grade['name']} from {grade_url}")

    response = make_request(grade_url, session=session)
    if not response:
        logger.warning(f"Failed to get details for grade: {grade['name']}")
        return grade

    soup = BeautifulSoup(response.text, "html.parser")

    # Extract season year from grade name or content
    season_year = extract_season_year(grade["name"], soup)
    grade["season"] = str(season_year)  # Store as string to match your data format

    # Extract grade type (Senior, Junior, etc.)
    grade["type"] = determine_competition_type("", grade["name"])

    # Extract gender
    grade["gender"] = determine_gender(grade["name"])

    # Add references to parent competition (following your structure)
    grade["competition_ref"] = {"__ref__": f"competitions/{grade['comp_id']}"}
    grade["parent_comp_ref"] = {"__ref__": f"competitions/{grade['comp_id']}"}

    return grade

def extract_season_year(name, soup):
    """Extract the season year from name or page content.

    Args:
        name: Name string
        soup: BeautifulSoup object of the page (can be None)

    Returns:
        int: Season year
    """
    # Try to extract year from name first (e.g., "Premier League - 2023")
    year_match = re.search(r'(20\d{2})', name)
    if year_match:
        return int(year_match.group(1))

    # Look for year in page header if soup is provided
    if soup:
        header_elements = soup.select("h1, h2, h3, h4")
        for element in header_elements:
            year_match = re.search(r'(20\d{2})', element.text)
            if year_match:
                return int(year_match.group(1))

    # Default to current year if not found
    return CURRENT_YEAR

def determine_competition_type(category, name):
    """Determine the competition type from category and name.

    Args:
        category: Competition category
        name: Competition name

    Returns:
        str: Competition type
    """
    # Check category first
    if category:
        category_lower = category.lower()
        if "junior" in category_lower:
            return "Junior"
        if "senior" in category_lower:
            return "Senior"
        if "master" in category_lower:
            return "Masters"

    # Check name
    name_lower = name.lower()
    if "junior" in name_lower or "under" in name_lower or "u1" in name_lower:
        return "Junior"
    if "senior" in name_lower or "premier" in name_lower or "pennant" in name_lower or "metro" in name_lower:
        return "Senior"
    if "master" in name_lower or "veteran" in name_lower or "35+" in name_lower or "45+" in name_lower:
        return "Masters"
    if "midweek" in name_lower:
        return "Midweek"
    if "indoor" in name_lower:
        return "Indoor"
    if "outdoor" in name_lower:
        return "Outdoor"

    # Default
    return "Other"

def determine_gender(name):
    """Determine gender from name.

    Args:
        name: Name string

    Returns:
        str: Gender (Men, Women, Mixed, or Unknown)
    """
    name_lower = name.lower()

    if any(term in name_lower for term in ["men", "male", "boys", "men's"]):
        return "Men"
    if any(term in name_lower for term in ["women", "female", "girls", "women's"]):
        return "Women"
    if "mixed" in name_lower:
        return "Mixed"

    return "Unknown"

def create_or_update_competition(db, comp, dry_run=False):
    """Create or update a competition in Firestore."""
    if dry_run:
        return True

    try:
        # Use the comp_id directly as the document ID
        comp_id = comp["id"]

        # Sanitize data for Firestore
        clean_data = sanitize_for_firestore(comp)

        # Log what we're about to write
        logger.debug(f"Writing competition {comp_id}: {clean_data}")

        comp_ref = db.collection("competitions").document(comp_id)
        comp_ref.set(clean_data, merge=True)
        return True
    except Exception as e:
        logger.error(f"Failed to save competition {comp.get('name', 'unknown')} (ID: {comp.get('id', 'unknown')}): {str(e)}")
        return False

def create_or_update_grade(db, grade, dry_run=False):
    """Create or update a grade in Firestore with proper references."""
    if dry_run:
        return True

    try:
        # Use the fixture_id directly as the document ID
        fixture_id = grade["id"]

        # Create document reference to parent competition if available
        if grade.get("parent_comp_id"):
            grade["competition_ref"] = db.collection("competitions").document(grade["parent_comp_id"])

        # Sanitize data for Firestore
        clean_data = sanitize_for_firestore(grade)

        # Log what we're about to write
        logger.debug(f"Writing grade {fixture_id}: {clean_data}")

        grade_ref = db.collection("grades").document(fixture_id)
        grade_ref.set(clean_data, merge=True)
        return True
    except Exception as e:
        logger.error(f"Failed to save grade {grade.get('name', 'unknown')} (ID: {grade.get('id', 'unknown')}): {str(e)}")
        return False

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Discover Hockey Victoria competitions and grades")

    parser.add_argument(
        "--season",
        type=int,
        default=CURRENT_YEAR,
        help=f"Season year to filter by (default: {CURRENT_YEAR})"
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
    global logger  # Make sure we're using the module-level logger
    logger = setup_logger("discover_competitions", log_level=log_level)

    try:
        # Initialize Firebase
        if not args.dry_run:
            logger.info("Initializing Firebase...")
            db = initialize_firebase(args.creds)
        else:
            logger.info("DRY RUN MODE - No database writes will be performed")
            db = None

        # Start discovery process
        start_time = datetime.now()
        logger.info(f"Starting competition discovery for season {args.season}")

        # Create a session for all requests
        import requests
        session = requests.Session()

        # Discover competition links
        competitions, grades = discover_competition_links(logger, session)

        if not competitions:
            logger.error("No competitions found. Exiting.")
            return 1

        # Filter by season if specified
        if args.season:
            logger.info(f"Filtering for season {args.season}")
            season_str = str(args.season)

            # Filter competitions
            filtered_competitions = {}
            for comp_id, comp in competitions.items():
                if season_str in comp["name"]:
                    filtered_competitions[comp_id] = comp

            # Filter grades
            filtered_grades = []
            for grade in grades:
                if season_str in grade["name"] or grade["comp_id"] in filtered_competitions:
                    filtered_grades.append(grade)

            logger.info(f"Found {len(filtered_competitions)} competitions and {len(filtered_grades)} grades for season {args.season}")
            competitions = filtered_competitions
            grades = filtered_grades

        # Process each competition
        comp_success_count = 0
        for comp_id, competition in competitions.items():
            logger.info(f"Processing competition {comp_id}: {competition['name']}")

            # Get additional details
            competition = get_competition_details(logger, competition, session)

            # Create/update in database
            if not args.dry_run:
                success = create_or_update_competition(db, competition)
                if success:
                    comp_success_count += 1
                    logger.info(f"Successfully saved competition: {competition['name']}")
                else:
                    logger.error(f"Failed to save competition: {competition['name']}")
            else:
                logger.info(f"[DRY RUN] Would save competition: {competition['name']}")
                comp_success_count += 1

        # Process each grade
        grade_success_count = 0
        for i, grade in enumerate(grades):
            logger.info(f"Processing grade {i+1}/{len(grades)}: {grade['name']} (ID: {grade['id']})")

            # Get additional details
            grade = get_grade_details(logger, grade, session)

            # Create/update in database
            if not args.dry_run:
                success = create_or_update_grade(db, grade)
                if success:
                    grade_success_count += 1
                    logger.info(f"Successfully saved grade: {grade['name']}")
                else:
                    logger.error(f"Failed to save grade: {grade['name']}")
            else:
                logger.info(f"[DRY RUN] Would save grade: {grade['name']}")
                grade_success_count += 1

            # Short delay to avoid hammering the server
            time.sleep(1)

        # Report results
        logger.info(f"Discovery completed. Processed {len(competitions)} competitions ({comp_success_count} successful) and {len(grades)} grades ({grade_success_count} successful).")
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