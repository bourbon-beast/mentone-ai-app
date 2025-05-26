from firebase_functions import https_fn
from firebase_admin import initialize_app

# Initialize Firebase
initialize_app()

# Import existing functions
from ladder_api import ladder_api
from travel_time import calculate_travel_time

# Import new functions
from discover_competitions_cf import discover_competitions_cf
from discover_games_cf import discover_games_cf
from discover_players_cf import discover_players_cf
from discover_teams_cf import discover_teams_cf
from extract_venues_cf import extract_venues_cf
from update_ladder_cf import update_ladder_cf
from update_results_cf import update_results_cf

# Export existing functions
# ladder_api = ladder_api # Retained as is from original, though direct use of imported name is also fine
# calculate_travel_time = calculate_travel_time # Retained as is

# Export new functions with specified endpoint names
discover_competitions = discover_competitions_cf
discover_games = discover_games_cf
discover_players = discover_players_cf
discover_teams = discover_teams_cf
extract_venues = extract_venues_cf
update_ladder = update_ladder_cf
update_results = update_results_cf