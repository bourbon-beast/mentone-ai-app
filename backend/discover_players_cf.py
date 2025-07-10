"""
Cloud Function to discover Hockey Victoria players for teams.
"""
import json
import re
import time
from datetime import datetime
from urllib.parse import urljoin

import firebase_admin
import requests
import pytz # For timezone handling
from bs4 import BeautifulSoup
from firebase_functions import https_fn
from firebase_admin import initialize_app, firestore

# --- Global Variables & Constants ---
try:
    firebase_admin.get_app()
except ValueError:
    initialize_app()

BASE_URL = "https://www.hockeyvictoria.org.au"
TEAM_STATS_URL_TEMPLATE = "https://www.hockeyvictoria.org.au/games/team-stats/{comp_id}?team={team_id}"
PLAYER_URL_PATTERN = re.compile(r"/games/statistics/([a-zA-Z0-9]+)") # HV Player ID
GAME_URL_PATTERN = re.compile(r"/game/(\d+)") # HV Game ID
DELAY_BETWEEN_REQUESTS_CF = 0.25  # seconds, shorter for CF environment

AUSTRALIA_TZ = pytz.timezone("Australia/Melbourne")

# --- CORS Headers ---
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

# --- Logging Setup (Simplified) ---
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO) # Default, can be changed by request param

# --- Utility Functions (Adapted or Inlined) ---
def make_request_cf(url, session=None, timeout=10):
    requester = session if session else requests.Session()
    try:
        response = requester.get(url, timeout=timeout)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for {url}: {e}")
        return None

def clean_text_cf(text):
    if text is None: return ""
    return text.strip().replace('\n', ' ').replace('\r', ' ')

def extract_number_cf(text, default=0):
    if text is None: return default
    match = re.search(r'\d+', str(text))
    return int(match.group(0)) if match else default

# --- Core Logic Functions (from discover_players.py, adapted for CF) ---

def discover_players_for_team_cf(team_info, db_client, dry_run_mode, session_obj):
    """
    Discovers players for a specific team, including per-game participation.
    team_info: Dict with team details (id, comp_id, name, gender).
    db_client: Firestore client.
    dry_run_mode: Boolean.
    session_obj: requests.Session object.
    """
    comp_id = team_info.get("comp_id")
    team_id = team_info.get("id") # Firestore team document ID
    team_name = team_info.get("name", "Unknown Team")
    team_hv_id = team_info.get("hv_id", team_id) # Hockey Victoria specific team ID, might be same as Firestore ID or different

    if not comp_id or not team_hv_id: # Use hv_id for URL construction
        logger.error(f"Team {team_name} ({team_id}): Missing comp_id ('{comp_id}') or Hockey Victoria team_id ('{team_hv_id}')")
        return [], 0, 0 # players, games_processed, players_saved_or_updated

    # The stats URL uses the Hockey Victoria team ID
    stats_url = TEAM_STATS_URL_TEMPLATE.format(comp_id=comp_id, team_id=team_hv_id)
    logger.info(f"Team {team_name} ({team_id}): Discovering players from HV URL: {stats_url}")

    response = make_request_cf(stats_url, session=session_obj)
    if not response:
        logger.error(f"Team {team_name} ({team_id}): Failed to get team stats page: {stats_url}")
        return [], 0, 0

    soup = BeautifulSoup(response.text, "html.parser")
    
    # --- Scrape Game Pages for Detailed Participation ---
    game_links_on_stats_page = set()
    for link_tag in soup.find_all("a", href=True):
        href = link_tag["href"]
        if GAME_URL_PATTERN.search(href): # Links like /games/game/12345
            full_url = urljoin(BASE_URL, href)
            game_links_on_stats_page.add(full_url)
    
    logger.info(f"Team {team_name} ({team_id}): Found {len(game_links_on_stats_page)} unique game links on stats page.")

    # game_participation_data: {player_hv_id: [{"game_id": ..., "round": ..., "stats": {...}}, ...]}
    game_participation_data = {} 
    # game_details_for_db: {game_hv_id: {"players": [{"player_id": ..., "name": ..., "stats":{}}], "round": ..., "teams_involved": [...]}}
    game_details_for_db = {} 
    games_processed_count = 0

    for game_idx, game_hv_url in enumerate(list(game_links_on_stats_page)):
        logger.debug(f"Team {team_name} ({team_id}): Processing game link {game_idx+1}/{len(game_links_on_stats_page)}: {game_hv_url}")
        game_response = make_request_cf(game_hv_url, session=session_obj)
        if not game_response:
            logger.warning(f"Team {team_name} ({team_id}): Failed to get game page: {game_hv_url}")
            continue

        game_soup = BeautifulSoup(game_response.text, "html.parser")
        game_hv_id_match = GAME_URL_PATTERN.search(game_hv_url)
        if not game_hv_id_match: 
            logger.warning(f"Team {team_name} ({team_id}): Could not extract game ID from URL {game_hv_url}")
            continue
        game_hv_id = game_hv_id_match.group(1)

        round_info_text = game_soup.find(text=re.compile(r"Round \d+", re.IGNORECASE))
        round_number = extract_number_cf(round_info_text, 0) if round_info_text else 0
        
        game_title_tag = game_soup.find("h1") or game_soup.find("h2")
        teams_in_game = [clean_text_cf(t) for t in game_title_tag.text.split(" vs ")] if game_title_tag else [team_name, "Opponent"]

        current_game_players_list = [] # For game_details_for_db

        player_tables_in_game = game_soup.select("table.table") # Expecting two tables, one per team
        for p_table in player_tables_in_game:
            headers = [clean_text_cf(th.text).lower() for th in p_table.select("thead th")]
            player_col_idx = next((i for i, h in enumerate(headers) if "player" in h or "name" in h), None)
            if player_col_idx is None: continue

            for p_row in p_table.select("tbody tr"):
                cells = p_row.select("td")
                if len(cells) <= player_col_idx: continue
                
                player_cell_content = cells[player_col_idx]
                player_name_scraped = clean_text_cf(player_cell_content.text)
                if not player_name_scraped or player_name_scraped.lower() in ["total", "team total"]: continue

                player_hv_id = None
                player_link_tag = player_cell_content.find("a", href=True) # Link to player's HV stats page
                if player_link_tag:
                    player_hv_id_match = PLAYER_URL_PATTERN.search(player_link_tag.get("href", ""))
                    if player_hv_id_match: player_hv_id = player_hv_id_match.group(1)
                
                if not player_hv_id:
                    logger.warning(f"Team {team_name}, Game {game_hv_id}: No HV ID for player '{player_name_scraped}'. Skipping.")
                    continue
                
                # Extract in-game stats if available
                player_game_stats = {
                    "goals": extract_number_cf(cells[next((i for i,h in enumerate(headers) if "goals" in h), -1)].text if next((i for i,h in enumerate(headers) if "goals"in h),-1)>-1 and len(cells)>next((i for i,h in enumerate(headers) if "goals"in h),-1) else "0"),
                    "green_cards": extract_number_cf(cells[next((i for i,h in enumerate(headers) if "green" in h), -1)].text if next((i for i,h in enumerate(headers) if "green"in h),-1)>-1 and len(cells)>next((i for i,h in enumerate(headers) if "green"in h),-1) else "0"),
                    "yellow_cards": extract_number_cf(cells[next((i for i,h in enumerate(headers) if "yellow" in h), -1)].text if next((i for i,h in enumerate(headers) if "yellow"in h),-1)>-1 and len(cells)>next((i for i,h in enumerate(headers) if "yellow"in h),-1) else "0"),
                    "red_cards": extract_number_cf(cells[next((i for i,h in enumerate(headers) if "red" in h), -1)].text if next((i for i,h in enumerate(headers) if "red"in h),-1)>-1 and len(cells)>next((i for i,h in enumerate(headers) if "red"in h),-1) else "0"),
                }

                # Store participation for this player
                if player_hv_id not in game_participation_data: game_participation_data[player_hv_id] = []
                game_participation_data[player_hv_id].append({
                    "game_id": game_hv_id, "round": round_number, 
                    "team_id": team_id, # Firestore team_id this game is associated with for this player
                    "stats": {"games_played": 1, **player_game_stats}
                })
                # Store player for this game's record
                current_game_players_list.append({"player_id": player_hv_id, "name": player_name_scraped, "stats": player_game_stats})
        
        # Store game details for saving to 'games' collection
        game_details_for_db[game_hv_id] = {
            "id": game_hv_id, "round": round_number, "teams_involved": teams_in_game,
            "associated_team_ids": [team_id], # List because a game could be relevant to multiple processed teams over time
            "players_participated": current_game_players_list,
            "url": game_hv_url,
            "updated_at": datetime.now(AUSTRALIA_TZ).astimezone(pytz.utc),
        }
        games_processed_count += 1
        time.sleep(DELAY_BETWEEN_REQUESTS_CF) # Polite delay

    # --- Process Overall Team Stats Page for Player Roster ---
    # This ensures even players who haven't played a game (zero stats) are captured if on roster.
    final_player_list_for_team = []
    player_tables_on_stats_page = soup.select("table.table") # Re-select tables from main stats page
    
    for table_idx, player_table in enumerate(player_tables_on_stats_page):
        headers = [clean_text_cf(th.text).lower() for th in player_table.select("thead th")]
        if not any(h in ["player", "name", "matches", "goals"] for h in headers): continue

        player_col_idx = next((i for i, h in enumerate(headers) if "player" in h or "name" in h), None)
        if player_col_idx is None: continue
        
        player_role_type = "field" # Default
        if any("keeper" in h or "goalie" in h for h in headers): player_role_type = "goalkeeper"

        for row_idx, p_row in enumerate(player_table.select("tbody tr")):
            cells = p_row.select("td")
            if len(cells) <= player_col_idx: continue

            player_name_roster = clean_text_cf(cells[player_col_idx].text)
            if not player_name_roster or player_name_roster.lower() in ["total", "team total"]: continue

            player_hv_id_roster = None
            player_link_roster = cells[player_col_idx].find("a", href=True)
            if player_link_roster:
                player_hv_id_match_roster = PLAYER_URL_PATTERN.search(player_link_roster.get("href",""))
                if player_hv_id_match_roster: player_hv_id_roster = player_hv_id_match_roster.group(1)
            
            if not player_hv_id_roster:
                logger.warning(f"Team {team_name} ({team_id}): No HV ID for roster player '{player_name_roster}'. Skipping.")
                continue

            # Aggregate stats from game participation scraped earlier
            aggregated_player_stats = {"games_played":0, "goals":0, "assists":0, "green_cards":0, "yellow_cards":0, "red_cards":0}
            player_games_list = []
            if player_hv_id_roster in game_participation_data:
                player_games_list = game_participation_data[player_hv_id_roster]
                for game_played_info in player_games_list:
                    for stat_key, val in game_played_info["stats"].items():
                        aggregated_player_stats[stat_key] = aggregated_player_stats.get(stat_key, 0) + val
            
            # Create player object for Firestore
            player_firestore_obj = {
                "id": player_hv_id_roster, # Use HV Player ID as Firestore Player ID
                "name": player_name_roster,
                "type": player_role_type, # field or goalkeeper
                "gender": team_info.get("gender", "Unknown"),
                "is_mentone_player": team_info.get("is_home_club", False), # True if this is a Mentone team
                "active": True,
                "stats_snapshot": aggregated_player_stats, # Stats specific to this team context / discovery session
                "games_snapshot": player_games_list, # Games played for this team in this context
                # 'teams' field will be managed by create_or_update_player_cf
                "updated_at": datetime.now(AUSTRALIA_TZ).astimezone(pytz.utc),
                # Pass team context for create_or_update function
                "_current_team_context": {
                    "id": team_id, # Firestore team ID
                    "name": team_name,
                    "comp_id": comp_id,
                    "hv_id": team_hv_id
                }
            }
            final_player_list_for_team.append(player_firestore_obj)
    
    logger.info(f"Team {team_name} ({team_id}): Processed roster, found {len(final_player_list_for_team)} players. Processed {games_processed_count} game pages.")

    # --- Save Game Details to Firestore ---
    # This saves/updates the 'games' collection with player participation from this team's perspective
    games_saved_this_run = 0
    for game_hv_id_key, game_detail_data in game_details_for_db.items():
        if not dry_run_mode:
            try:
                game_doc_ref = db_client.collection("games").document(game_hv_id_key)
                existing_game_data = game_doc_ref.get()
                if existing_game_data.exists: # Merge associated team_ids
                    existing_assoc_teams = existing_game_data.to_dict().get("associated_team_ids", [])
                    if team_id not in existing_assoc_teams:
                        game_detail_data["associated_team_ids"] = list(set(existing_assoc_teams + [team_id]))
                game_doc_ref.set(game_detail_data, merge=True)
                games_saved_this_run +=1
            except Exception as e_game_save:
                logger.error(f"Team {team_name} ({team_id}): Failed to save game data for {game_hv_id_key}: {e_game_save}")
        else:
            games_saved_this_run +=1 # Count as "saved" in dry run
    logger.info(f"Team {team_name} ({team_id}): Saved/updated {games_saved_this_run} game documents.")
            
    return final_player_list_for_team, games_processed_count, games_saved_this_run


def create_or_update_player_cf(db_client, player_data, dry_run_mode):
    """
    Create or update a player in Firestore. Player data is keyed by HV Player ID.
    Handles merging stats if player plays for multiple teams.
    player_data contains _current_team_context.
    """
    player_hv_id = player_data["id"]
    player_ref = db_client.collection("players").document(player_hv_id)
    
    current_team_ctx = player_data.pop("_current_team_context") # Extract context, don't save it directly

    if dry_run_mode:
        logger.info(f"[DRY RUN] Would save player: {player_data.get('name')} (ID: {player_hv_id}) for team {current_team_ctx['name']}.")
        return True

    try:
        now_utc = datetime.now(AUSTRALIA_TZ).astimezone(pytz.utc)
        player_doc = player_ref.get()

        if player_doc.exists: # Player exists, merge data
            existing_data = player_doc.to_dict()
            
            # Merge top-level fields (name, gender, type, active status can be updated)
            updated_data = {
                "name": player_data.get("name", existing_data.get("name")),
                "gender": player_data.get("gender", existing_data.get("gender", "Unknown")),
                "type": player_data.get("type", existing_data.get("type", "field")),
                "is_mentone_player": existing_data.get("is_mentone_player") or player_data.get("is_mentone_player", False),
                "active": True, # Assume active if discovered
                "updated_at": now_utc,
                "created_at": existing_data.get("created_at", now_utc), # Preserve original creation
                "stats_all_teams": existing_data.get("stats_all_teams", {"games_played":0, "goals":0, "assists":0, "green_cards":0, "yellow_cards":0, "red_cards":0}),
                "games_all_teams": existing_data.get("games_all_teams", []),
                "teams": existing_data.get("teams", [])
            }

            # Aggregate overall stats ('stats_all_teams')
            # The stats_snapshot from player_data is from ONE team context.
            # This part needs careful thought: if we run this for Team A then Team B,
            # stats_snapshot from Team B should contribute to stats_all_teams.
            # For simplicity here, we assume stats_snapshot IS the new contribution.
            # A more robust way would be to only add diffs or recalculate from games_all_teams.
            new_contribution_stats = player_data.get("stats_snapshot", {})
            for stat_key, val in new_contribution_stats.items():
                 updated_data["stats_all_teams"][stat_key] = updated_data["stats_all_teams"].get(stat_key, 0) + val
            
            # Merge games list ('games_all_teams')
            # Add games from player_data["games_snapshot"] if not already present by game_id
            existing_game_ids = {g["game_id"] for g in updated_data["games_all_teams"]}
            for game_to_add in player_data.get("games_snapshot", []):
                if game_to_add["game_id"] not in existing_game_ids:
                    updated_data["games_all_teams"].append(game_to_add)
                    existing_game_ids.add(game_to_add["game_id"]) # Ensure it's added only once per run

            # Update 'teams' list (list of teams player is associated with)
            current_team_ref_str = f"teams/{current_team_ctx['id']}"
            team_already_listed = any(t.get("id") == current_team_ctx["id"] for t in updated_data["teams"])
            if not team_already_listed:
                updated_data["teams"].append({
                    "id": current_team_ctx["id"], "name": current_team_ctx["name"], 
                    "comp_id": current_team_ctx["comp_id"], "hv_id": current_team_ctx["hv_id"],
                    "team_ref_str": current_team_ref_str
                })
            
            player_ref.set(updated_data, merge=True)
            logger.debug(f"Player {player_hv_id} updated for team {current_team_ctx['name']}.")

        else: # New player
            player_data["created_at"] = now_utc
            player_data["stats_all_teams"] = player_data.pop("stats_snapshot", {"games_played":0, "goals":0, "assists":0, "green_cards":0, "yellow_cards":0, "red_cards":0})
            player_data["games_all_teams"] = player_data.pop("games_snapshot", [])
            player_data["teams"] = [{
                "id": current_team_ctx["id"], "name": current_team_ctx["name"],
                "comp_id": current_team_ctx["comp_id"], "hv_id": current_team_ctx["hv_id"],
                "team_ref_str": f"teams/{current_team_ctx['id']}"
            }]
            # Remove any other temporary fields if necessary
            player_ref.set(player_data)
            logger.debug(f"New player {player_hv_id} created for team {current_team_ctx['name']}.")
        return True
        
    except Exception as e_save:
        logger.error(f"Failed to save player {player_hv_id} (Name: {player_data.get('name')}): {e_save}", exc_info=True)
        return False

# --- Cloud Function Entry Point ---
@https_fn.on_request()
def discover_players_cf(req: https_fn.Request) -> https_fn.Response:
    if req.method == 'OPTIONS':
        return https_fn.Response("", status=204, headers=CORS_HEADERS)

    log_level_param = req.args.get("log_level", "INFO").upper()
    logger.setLevel(getattr(logging, log_level_param, logging.INFO))
    logger.info(f"discover_players_cf triggered. Log level: {log_level_param}")

    db = firestore.client()

    # Request Parameters
    team_id_param = req.args.get("team_id") # Firestore team document ID
    dry_run_param = req.args.get("dry_run", "false").lower() == "true"
    mentone_teams_only_param = req.args.get("mentone_only", "true").lower() == "true"
    limit_teams_param = req.args.get("limit_teams", type=int)

    teams_to_query = []
    try:
        teams_collection = db.collection("teams")
        if team_id_param:
            logger.info(f"Fetching specific team by Firestore ID: {team_id_param}")
            team_doc = teams_collection.document(team_id_param).get()
            if team_doc.exists:
                teams_to_query.append({"id": team_doc.id, **team_doc.to_dict()})
            else:
                return https_fn.Response(json.dumps({"status":"error", "message":f"Team with Firestore ID {team_id_param} not found."}),
                                       status=404, mimetype="application/json", headers=CORS_HEADERS)
        else:
            query = teams_collection
            if mentone_teams_only_param:
                query = query.where("is_home_club", "==", True)
            if limit_teams_param and limit_teams_param > 0:
                query = query.limit(limit_teams_param)
            
            for team_doc in query.stream():
                teams_to_query.append({"id": team_doc.id, **team_doc.to_dict()})
            logger.info(f"Fetched {len(teams_to_query)} teams. Mentone only: {mentone_teams_only_param}, Limit: {limit_teams_param}")

        if not teams_to_query:
            return https_fn.Response(json.dumps({"status":"success", "message":"No teams found to process based on parameters."}),
                                   status=200, mimetype="application/json", headers=CORS_HEADERS)

        overall_start_time = time.time()
        session = requests.Session()
        
        total_players_processed_count = 0 # Unique players saved/updated
        total_game_pages_scraped_count = 0
        total_game_docs_saved_count = 0
        teams_fully_processed_count = 0
        error_count = 0
        
        # Keep track of players updated in this run to count unique players
        players_updated_in_this_run = set()

        for i, team_data_from_db in enumerate(teams_to_query):
            team_name_log = team_data_from_db.get('name', team_data_from_db.get('id', f'Unknown Team {i+1}'))
            logger.info(f"Processing team {i+1}/{len(teams_to_query)}: {team_name_log}")
            start_time_team = time.time()
            try:
                # discover_players_for_team_cf returns: players_list, games_scraped_count, game_docs_saved_count
                players_found_for_team, games_scraped, game_docs_saved = discover_players_for_team_cf(
                    team_data_from_db, db, dry_run_param, session
                )
                total_game_pages_scraped_count += games_scraped
                total_game_docs_saved_count += game_docs_saved

                for player_obj in players_found_for_team:
                    if create_or_update_player_cf(db, player_obj, dry_run_param):
                        players_updated_in_this_run.add(player_obj["id"])
                    else:
                        error_count += 1 # Error during player save

                teams_fully_processed_count += 1
                logger.info(f"Team {team_name_log} processed in {time.time() - start_time_team:.2f}s. Found {len(players_found_for_team)} player entries for this team context.")
            except Exception as e_team_proc:
                logger.error(f"Error processing team {team_name_log}: {e_team_proc}", exc_info=True)
                error_count += 1
            
            if i < len(teams_to_query) - 1: time.sleep(DELAY_BETWEEN_REQUESTS_CF * 2) # Slightly longer delay between teams

        total_players_processed_count = len(players_updated_in_this_run)
        duration_overall = time.time() - overall_start_time
        summary_msg = (
            f"Player discovery finished in {duration_overall:.2f}s. "
            f"Teams processed: {teams_fully_processed_count}/{len(teams_to_query)}. "
            f"Unique players saved/updated: {total_players_processed_count}. "
            f"Game pages scraped: {total_game_pages_scraped_count}. Game documents saved: {total_game_docs_saved_count}. "
            f"Errors: {error_count}."
        )
        logger.info(summary_msg)
        if dry_run_param: logger.info("DRY RUN active. No actual database writes occurred.")

        return https_fn.Response(
            json.dumps({
                "status": "success", "message": summary_msg,
                "data": {
                    "teams_queried": len(teams_to_query),
                    "teams_processed": teams_fully_processed_count,
                    "unique_players_saved_or_updated": total_players_processed_count,
                    "game_pages_scraped": total_game_pages_scraped_count,
                    "game_documents_saved_or_dryrun": total_game_docs_saved_count,
                    "errors": error_count,
                    "duration_seconds": round(duration_overall, 2),
                    "dry_run": dry_run_param
                }
            }),
            status=200, mimetype="application/json", headers=CORS_HEADERS
        )

    except Exception as e_main_handler:
        logger.error(f"Critical error in discover_players_cf main handler: {str(e_main_handler)}", exc_info=True)
        return https_fn.Response(
            json.dumps({"status": "error", "message": f"Critical error: {str(e_main_handler)}"}),
            status=500, mimetype="application/json", headers=CORS_HEADERS
        )
