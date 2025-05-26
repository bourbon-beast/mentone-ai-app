"""
Hockey Victoria Player Discovery Script

This script discovers player data for Mentone Hockey Club by:
1. Getting player statistics from team pages on Hockey Victoria website
2. Scraping individual game pages for per-round participation
3. Saving player data to Firestore with support for multiple teams
4. Storing game metadata and player participation in a games collection

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
PLAYER_URL_PATTERN = re.compile(r"/games/statistics/([a-zA-Z0-9]+)")
GAME_URL_PATTERN = re.compile(r"/game/(\d+)")
DELAY_BETWEEN_REQUESTS = 1  # seconds

def discover_players_for_team(logger, team, db, dry_run=False, session=None):
    """Discover players for a specific team, including per-game participation.

    Args:
        logger: Logger instance
        team: Team dictionary containing comp_id and id
        db: Firestore client
        dry_run: If True, don't write to database
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

    # Find game links on the team stats page
    game_links = set()
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if GAME_URL_PATTERN.search(href):
            full_url = urljoin(BASE_URL, href)
            game_links.add(full_url)

    logger.info(f"Found {len(game_links)} game links for team: {team_name}")

    # Scrape each game page for player participation and round info
    game_participation = {}  # {player_id: [{"game_id": ..., "round": ..., "stats": {...}}, ...]}
    game_players = {}  # {game_id: [{"player_id": ..., "name": ..., "stats": {...}}, ...]}

    for game_url in game_links:
        game_response = make_request(game_url, session=session)
        if not game_response:
            logger.error(f"Failed to get game page: {game_url}")
            continue

        game_soup = BeautifulSoup(game_response.text, "html.parser")
        game_id = GAME_URL_PATTERN.search(game_url).group(1)

        # Extract round number
        round_info = game_soup.find(text=re.compile(r"Round \d+"))
        round_number = extract_number(round_info, 0) if round_info else 0
        logger.debug(f"Processing game {game_id}, Round {round_number}")

        # Extract teams involved
        game_title = game_soup.find("h1") or game_soup.find("h2")
        teams_involved = []
        if game_title:
            teams_involved = [clean_text(t) for t in game_title.text.split(" vs ")]
            if len(teams_involved) != 2:
                teams_involved = [team_name, "Opponent"]

        # Initialize game players list
        game_players[game_id] = []

        # Find player tables (two: one for each team)
        game_tables = game_soup.select("table.table")
        for table in game_tables:
            headers = [clean_text(th.text).lower() for th in table.select("thead th")]
            if "player" not in headers and "name" not in headers:
                continue

            player_col = next((i for i, h in enumerate(headers) if "player" in h or "name" in h), None)
            goals_col = next((i for i, h in enumerate(headers) if "goals" in h), None)
            green_cards_col = next((i for i, h in enumerate(headers) if "green" in h), None)
            yellow_cards_col = next((i for i, h in enumerate(headers) if "yellow" in h), None)
            red_cards_col = next((i for i, h in enumerate(headers) if "red" in h), None)

            if player_col is None:
                continue

            rows = table.select("tbody tr")
            for row in rows:
                cells = row.select("td")
                if len(cells) <= player_col:
                    continue

                player_cell = cells[player_col]
                player_name = clean_text(player_cell.text)
                if not player_name or player_name.lower() in ["total", "team total"]:
                    continue

                player_id = None
                player_link = player_cell.find("a", recursive=True)
                if player_link:
                    href = player_link.get("href", "")
                    full_url = urljoin(BASE_URL, href)
                    player_match = PLAYER_URL_PATTERN.search(full_url)
                    if player_match:
                        player_id = player_match.group(1)
                    else:
                        logger.warning(f"Could not extract ID from href: {full_url} for player: {player_name}")
                        continue
                else:
                    logger.warning(f"No <a> tag found for player: {player_name} in game: {game_id}")
                    continue

                if not player_id:
                    logger.warning(f"Skipping player {player_name} in game {game_id} due to missing Hockey Victoria ID")
                    continue

                game_stats = {
                    "games_played": 1,
                    "goals": extract_number(cells[goals_col].text, 0) if goals_col is not None and len(cells) > goals_col else 0,
                    "assists": 0,
                    "green_cards": extract_number(cells[green_cards_col].text, 0) if green_cards_col is not None and len(cells) > green_cards_col else 0,
                    "yellow_cards": extract_number(cells[yellow_cards_col].text, 0) if yellow_cards_col is not None and len(cells) > yellow_cards_col else 0,
                    "red_cards": extract_number(cells[red_cards_col].text, 0) if red_cards_col is not None and len(cells) > red_cards_col else 0,
                }

                # Add to player's game participation
                if player_id not in game_participation:
                    game_participation[player_id] = []
                game_participation[player_id].append({
                    "game_id": game_id,
                    "round": round_number,
                    "stats": game_stats
                })

                # Add to game's player list
                game_players[game_id].append({
                    "player_id": player_id,
                    "name": player_name,
                    "stats": game_stats
                })

        # Save game metadata and players to games collection
        game_data = {
            "id": game_id,
            "round": round_number,
            "teams": teams_involved,
            "team_ids": [team_id],
            "players": game_players[game_id],
            "updated_at": datetime.now(),
            "created_at": datetime.now()
        }
        if not dry_run and db:
            try:
                game_ref = db.collection("games").document(game_id)
                game_ref.set(game_data, merge=True)
                logger.debug(f"Saved game {game_id} with {len(game_players[game_id])} players")
            except Exception as e:
                logger.error(f"Failed to save game {game_id}: {e}")

        time.sleep(DELAY_BETWEEN_REQUESTS)

    # Process team stats page for players (ensure we capture all players)
    players = []
    player_tables = soup.select("table.table")
    for table_idx, table in enumerate(player_tables):
        headers = [clean_text(th.text).lower() for th in table.select("thead th")]
        if not any(header in ["player", "name", "matches", "goals", "attended"] for header in headers):
            continue

        player_col = next((i for i, h in enumerate(headers) if "player" in h or "name" in h), None)
        if player_col is None:
            logger.warning(f"Missing player column in table {table_idx+1}")
            continue

        player_type = "field"
        for header in headers:
            if "keeper" in header or "goalie" in header:
                player_type = "goalkeeper"
                break

        rows = table.select("tbody tr")
        for row_idx, row in enumerate(rows):
            try:
                cells = row.select("td")
                if len(cells) <= player_col:
                    continue

                player_cell = cells[player_col]
                player_name = clean_text(player_cell.text)
                if not player_name or player_name.lower() in ["total", "team total"]:
                    continue

                player_id = None
                player_link = player_cell.find("a", recursive=True)
                if player_link:
                    href = player_link.get("href", "")
                    full_url = urljoin(BASE_URL, href)
                    player_match = PLAYER_URL_PATTERN.search(full_url)
                    if player_match:
                        player_id = player_match.group(1)
                    else:
                        logger.warning(f"Could not extract ID from href: {full_url} for player: {player_name}")
                        continue
                else:
                    logger.warning(f"No <a> tag found for player: {player_name} in team: {team_name}")
                    continue

                if not player_id:
                    logger.warning(f"Skipping player {player_name} due to missing Hockey Victoria ID")
                    continue

                # Aggregate stats from game participation
                if player_id in game_participation:
                    aggregated_stats = {
                        "games_played": 0,
                        "goals": 0,
                        "assists": 0,
                        "green_cards": 0,
                        "yellow_cards": 0,
                        "red_cards": 0
                    }
                    for game in game_participation[player_id]:
                        for stat_key, stat_value in game["stats"].items():
                            aggregated_stats[stat_key] += stat_value
                    games_list = game_participation[player_id]
                else:
                    # Player might not have played but is on the team roster
                    aggregated_stats = {
                        "games_played": 0,
                        "goals": 0,
                        "assists": 0,
                        "green_cards": 0,
                        "yellow_cards": 0,
                        "red_cards": 0
                    }
                    games_list = []

                player = {
                    "id": player_id,
                    "name": player_name,
                    "team_id": team_id,
                    "team_name": team_name,
                    "type": player_type,
                    "gender": team.get("gender", "Unknown"),
                    "is_mentone_player": True,
                    "active": True,
                    "stats": aggregated_stats,
                    "games": games_list,
                    "updated_at": datetime.now(),
                    "created_at": datetime.now()
                }

                player["team_ref"] = {"__ref__": f"teams/{team_id}"}
                players.append(player)
                logger.debug(f"Found player: {player_name} (ID: {player_id}, Games: {aggregated_stats['games_played']}, Goals: {aggregated_stats['goals']})")

            except Exception as e:
                logger.error(f"Error processing player row {row_idx+1}: {e}")
                continue

    logger.info(f"Found {len(players)} players for team: {team_name}")
    return players

def create_or_update_player(db, player, dry_run=False):
    """Create or update a player in Firestore, aggregating stats across teams.

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
        player_id = player["id"]
        player_ref = db.collection("players").document(player_id)
        player_doc = player_ref.get()

        if "__ref__" in player.get("team_ref", {}):
            ref_path = player["team_ref"]["__ref__"]
            player["team_ref"] = db.document(ref_path)

        if player_doc.exists:
            existing_data = player_doc.to_dict()
            updated_data = existing_data.copy()

            # Aggregate stats across teams
            if "stats" in existing_data and "stats" in player:
                existing_stats = existing_data["stats"]
                new_stats = player["stats"]
                aggregated_stats = {}
                for stat_key in ["games_played", "goals", "assists", "green_cards", "yellow_cards", "red_cards"]:
                    existing_value = existing_stats.get(stat_key, 0)
                    new_value = new_stats.get(stat_key, 0)
                    aggregated_stats[stat_key] = existing_value + new_value
                updated_data["stats"] = aggregated_stats

            # Merge games list
            existing_games = existing_data.get("games", [])
            new_games = player.get("games", [])
            game_ids = {game["game_id"] for game in existing_games}
            for new_game in new_games:
                if new_game["game_id"] not in game_ids:
                    existing_games.append(new_game)
                    game_ids.add(new_game["game_id"])
            updated_data["games"] = existing_games

            # Update teams list
            teams = existing_data.get("teams", [])
            new_team = {"id": player["team_id"], "name": player["team_name"]}
            if not any(t.get("id") == new_team["id"] for t in teams):
                teams.append(new_team)
            updated_data["teams"] = teams

            if "primary_team_id" not in existing_data:
                updated_data["primary_team_id"] = player["team_id"]
                updated_data["primary_team_name"] = player["team_name"]
                updated_data["primary_team_ref"] = player["team_ref"]
            else:
                if "primary_team_ref" not in existing_data and "primary_team_id" in existing_data:
                    updated_data["primary_team_ref"] = db.document(f"teams/{existing_data['primary_team_id']}")

            updated_data["created_at"] = existing_data.get("created_at", player["created_at"])
            updated_data["updated_at"] = player["updated_at"]
            updated_data["name"] = player["name"]
            updated_data["gender"] = player.get("gender", existing_data.get("gender", "Unknown"))
            updated_data["type"] = player.get("type", existing_data.get("type", "field"))
            updated_data["is_mentone_player"] = True
            updated_data["active"] = True

            player_ref.set(updated_data, merge=True)
            return True
        else:
            player["teams"] = [{"id": player["team_id"], "name": player["team_name"]}]
            player["primary_team_id"] = player["team_id"]
            player["primary_team_name"] = player["team_name"]
            player["primary_team_ref"] = player["team_ref"]
            del player["team_id"]
            del player["team_name"]
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

    log_level = "DEBUG" if args.verbose else "INFO"
    global logger
    logger = setup_logger("discover_players", log_level=log_level)

    try:
        if not args.dry_run:
            logger.info("Initializing Firebase...")
            db = initialize_firebase(args.creds)
        else:
            logger.info("DRY RUN MODE - No database writes will be performed")
            db = None

        import requests
        session = requests.Session()

        start_time = datetime.now()

        if args.team_id:
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
            teams_query = db.collection("teams").where("is_home_club", "==", True).stream()
            teams = [{
                "id": team.id,
                "comp_id": team.get("comp_id"),
                "name": team.get("name"),
                "gender": team.get("gender"),
                "is_home_club": True
            } for team in teams_query]
            logger.info(f"Processing players for {len(teams)} Mentone teams")

        players_found = 0
        teams_processed = 0

        for team in teams:
            team_id = team["id"]
            team_name = team["name"]
            logger.info(f"Processing players for team: {team_name} (ID: {team_id})")

            players = discover_players_for_team(logger, team, db, args.dry_run, session)

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
            time.sleep(DELAY_BETWEEN_REQUESTS)

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