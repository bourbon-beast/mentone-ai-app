#!/usr/bin/env python
"""
Venue Extraction Script for Mentone Hockey Club

This script extracts venue information from Hockey Victoria game pages
and stores it in Firestore for use in the Travel Planner feature.
"""

import argparse
import sys
import re
import time
from datetime import datetime
from bs4 import BeautifulSoup
import requests
import logging

# Import utility modules
from backend.utils.firebase_init import initialize_firebase
from backend.utils.request_utils import make_request, create_session
from backend.utils.logging_utils import setup_logger
from backend.utils.parsing_utils import clean_text, save_debug_html

# Constants
BASE_URL = "https://www.hockeyvictoria.org.au"
DELAY_BETWEEN_REQUESTS = 1.5  # seconds, to avoid rate limiting

# Set up logger
logger = setup_logger("extract_venues")

def extract_venue_info(soup):
    """Extract venue information from a game detail page.

    Args:
        soup: BeautifulSoup object of the game page

    Returns:
        dict: Venue information dictionary or None if not found
    """
    # Find the venue section - look for div containing the word "Venue"
    venue_sections = soup.find_all(lambda tag: tag.name == 'div' and
                                               tag.find(text=re.compile(r'Venue', re.IGNORECASE)))

    if not venue_sections:
        logger.warning("No venue section found on page")
        return None

    venue_data = {}

    for section in venue_sections:
        # Get the containing row that has the venue info
        parent_row = section.find_parent('div', class_='row')
        if not parent_row:
            continue

        # Extract venue name - it's typically the text right after the "Venue" label
        venue_div = section.find_parent('div')
        if venue_div:
            # Get all text and remove the label "Venue"
            full_text = venue_div.get_text(strip=True)
            venue_name = re.sub(r'Venue', '', full_text, flags=re.IGNORECASE).strip()
            venue_data['name'] = venue_name

            # Try to find the address which is typically in a smaller font div
            address_div = venue_div.find('div', class_='font-size-sm')
            if address_div:
                venue_data['address'] = clean_text(address_div.get_text())

        # Look for field information
        field_section = parent_row.find(lambda tag: tag.name == 'div' and
                                                    tag.find(text=re.compile(r'Field', re.IGNORECASE)))
        if field_section:
            field_div = field_section.find_parent('div')
            if field_div:
                field_text = field_div.get_text(strip=True)
                field_code = re.sub(r'Field', '', field_text, flags=re.IGNORECASE).strip()
                venue_data['field_code'] = field_code

    # If we found a venue name, add additional fields
    if 'name' in venue_data:
        venue_data['created_at'] = datetime.now()
        venue_data['updated_at'] = datetime.now()

        # Generate a venue_code from the name (for easier lookups)
        venue_code = re.sub(r'[^a-zA-Z0-9]', '', venue_data['name'])
        venue_code = venue_code.upper()[:10]  # First 10 alphanumeric chars
        venue_data['venue_code'] = venue_code

        return venue_data

    return None

def extract_venues_from_games(db, game_urls, dry_run=False, max_games=None):
    """Extract venue information from a list of game URLs.

    Args:
        db: Firestore client
        game_urls: List of game detail URLs
        dry_run: If True, don't write to database
        max_games: Maximum number of games to process (for testing)

    Returns:
        tuple: (success_count, error_count, venues)
    """
    success_count = 0
    error_count = 0
    venues = {}  # Dictionary to track unique venues by name

    # Create a session for reuse
    session = create_session()

    # Limit the number of games if specified
    urls_to_process = game_urls
    if max_games and max_games > 0:
        urls_to_process = game_urls[:max_games]

    logger.info(f"Processing {len(urls_to_process)} game URLs")

    for i, url in enumerate(urls_to_process):
        try:
            logger.info(f"Processing game {i+1}/{len(urls_to_process)}: {url}")

            # Fetch the game page
            response = make_request(url, session=session)
            if not response:
                logger.error(f"Failed to fetch game page: {url}")
                error_count += 1
                continue

            # Parse with BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract venue information
            venue_data = extract_venue_info(soup)

            if not venue_data:
                logger.warning(f"No venue data found for game: {url}")
                error_count += 1
                continue

            # Check if we've already seen this venue (by name)
            if venue_data['name'] in venues:
                logger.info(f"Duplicate venue found: {venue_data['name']}")
                # Update stats but don't store again
                success_count += 1
            else:
                # Store unique venue
                venues[venue_data['name']] = venue_data

                if not dry_run:
                    # Store in Firestore
                    venue_ref = save_venue_to_firestore(db, venue_data)
                    logger.info(f"Saved venue: {venue_data['name']} (ID: {venue_ref.id})")
                else:
                    logger.info(f"[DRY RUN] Would save venue: {venue_data['name']}")

                success_count += 1

            # Sleep to avoid hammering the server
            time.sleep(DELAY_BETWEEN_REQUESTS)

        except Exception as e:
            logger.error(f"Error processing game {url}: {str(e)}")
            error_count += 1

    return success_count, error_count, venues

def save_venue_to_firestore(db, venue_data):
    """Save venue information to Firestore.

    Args:
        db: Firestore client
        venue_data: Venue information dictionary

    Returns:
        DocumentReference: Firestore reference to the saved venue
    """
    # Use venue code as the document ID if available, otherwise auto-generate
    venue_code = venue_data.get('venue_code')

    if venue_code:
        venue_ref = db.collection('venues').document(venue_code)
        venue_ref.set(venue_data, merge=True)
    else:
        venue_ref = db.collection('venues').add(venue_data)[1]

    return venue_ref

def discover_game_urls(db, limit=100):
    """Get game URLs from the Firestore database.

    Args:
        db: Firestore client
        limit: Maximum number of games to retrieve

    Returns:
        list: List of game URLs
    """
    game_urls = []

    try:
        # Query recent games that have Mentone playing
        games_ref = db.collection('games')
        query = (games_ref
                 .where('mentone_playing', '==', True)
                 .limit(limit))

        games = query.stream()

        for game in games:
            game_data = game.to_dict()
            # Check if the game has a URL
            url = game_data.get('url')
            if url and url.startswith('https://'):
                game_urls.append(url)

    except Exception as e:
        logger.error(f"Error fetching games from Firestore: {str(e)}")

    logger.info(f"Found {len(game_urls)} game URLs in Firestore")
    return game_urls

def fetch_missing_venue_data(db):
    """Fetch missing venue data for games that have a venue name but no address.

    Args:
        db: Firestore client

    Returns:
        int: Number of venues updated
    """
    updated_count = 0

    try:
        # Query games that have a venue but might be missing full venue details
        games_ref = db.collection('games')
        query = (games_ref
                 .where('venue', '!=', None)
                 .limit(500))  # Process in batches if needed

        games = list(query.stream())
        logger.info(f"Found {len(games)} games with venue names to check")

        # Create a session for reuse
        session = create_session()

        # Track processed venues to avoid duplicates
        processed_venues = set()

        for game in games:
            game_data = game.to_dict()
            venue_name = game_data.get('venue')

            # Skip if no venue or if we've already processed this venue
            if not venue_name or venue_name in processed_venues:
                continue

            processed_venues.add(venue_name)

            # Check if we already have this venue with full details
            venue_query = (db.collection('venues')
                           .where('name', '==', venue_name)
                           .limit(1))

            venues = list(venue_query.stream())

            # If venue exists with an address, skip it
            if venues and 'address' in venues[0].to_dict():
                continue

            # If we have a game URL, fetch the venue details
            url = game_data.get('url')
            if url and url.startswith('https://'):
                logger.info(f"Fetching venue details for {venue_name} from {url}")

                # Fetch the game page
                response = make_request(url, session=session)
                if not response:
                    logger.error(f"Failed to fetch game page: {url}")
                    continue

                # Parse with BeautifulSoup
                soup = BeautifulSoup(response.text, 'html.parser')

                # Extract venue information
                venue_data = extract_venue_info(soup)

                if venue_data and 'address' in venue_data:
                    # Store in Firestore
                    venue_ref = save_venue_to_firestore(db, venue_data)
                    logger.info(f"Updated venue: {venue_data['name']} with address: {venue_data['address']}")
                    updated_count += 1

                # Sleep to avoid hammering the server
                time.sleep(DELAY_BETWEEN_REQUESTS)

    except Exception as e:
        logger.error(f"Error updating venues: {str(e)}")

    return updated_count

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Extract venue information from Hockey Victoria game pages")

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
        "--max-games",
        type=int,
        default=0,
        help="Maximum number of games to process (0 for all)"
    )

    parser.add_argument(
        "--update-missing",
        action="store_true",
        help="Update games with venues that have missing address data"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    try:
        # Initialize Firebase
        logger.info("Initializing Firebase...")
        db = initialize_firebase(args.creds)

        if args.update_missing:
            # Update games with missing venue details
            logger.info("Updating games with missing venue details...")
            updated_count = fetch_missing_venue_data(db)
            logger.info(f"Updated {updated_count} venues with missing details")
        else:
            # Regular venue extraction process
            logger.info("Starting venue extraction process")

            # Get game URLs from Firestore
            game_urls = discover_game_urls(db, limit=500)

            if not game_urls:
                logger.error("No game URLs found in database. Exiting.")
                return 1

            # Extract venue information from each game
            success_count, error_count, venues = extract_venues_from_games(
                db, game_urls, args.dry_run, args.max_games)

            logger.info(f"Extraction completed. Success: {success_count}, Errors: {error_count}")
            logger.info(f"Found {len(venues)} unique venues")

            # Print summary of venues found
            for venue_name, venue_data in venues.items():
                address = venue_data.get('address', 'No address')
                field = venue_data.get('field_code', 'No field code')
                logger.info(f"Venue: {venue_name}, Address: {address}, Field: {field}")

        return 0

    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        return 130
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())