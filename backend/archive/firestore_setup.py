import firebase_admin
from firebase_admin import credentials, firestore
import json
from datetime import datetime, timedelta
import os

# Initialize Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate("../secrets/serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

def setup_collections():
    """Set up all collections in Firestore based on mentone_teams.json"""
    # Delete existing documents first
    collections = ["competitions", "grades", "teams", "games", "players", "settings"]
    for collection in collections:
        docs = db.collection(collection).stream()
        for doc in docs:
            doc.reference.delete()
        print(f"Deleted all documents in {collection}")

    # Load team data from JSON
    with open("../mentone_teams.json", "r") as f:
        teams_data = json.load(f)

    # Setup collections
    setup_competitions_and_grades(teams_data)
    setup_teams(teams_data)
    setup_sample_games()
    setup_players()
    setup_settings()

    print("Firestore collections setup complete!")

def setup_competitions_and_grades(teams_data):
    """Create competitions and grades collections from team data with improved key structure"""
    print("Setting up competitions and grades collections...")

    # Extract unique competitions and grades
    competitions = {}
    grades = {}

    for team in teams_data:
        comp_id = team["comp_id"]
        fixture_id = team["fixture_id"]
        team_type = team["type"]  # Now properly set by builder.py

        # Process competition if new
        if comp_id not in competitions:
            # Get season from comp name
            comp_parts = team["comp_name"].split(" - ")
            season = comp_parts[1] if len(comp_parts) > 1 else "2025"

            # Create a unique competition ID that combines type and comp_id
            composite_id = f"comp_{team_type.lower()}_{comp_id}"

            # Determine the competition name
            competition_name = f"{season} {team_type} Competition"

            competitions[comp_id] = {
                "id": composite_id,
                "comp_id": comp_id,  # Still keep the original ID for URL construction
                "name": competition_name,
                "type": team_type,
                "season": season,
                "start_date": "2025-03-15",  # Placeholder
                "end_date": "2025-09-20",    # Placeholder
                "rounds": 18                 # Placeholder
            }

        # Process grade if new
        if fixture_id not in grades:
            # Extract grade name from comp name
            comp_parts = team["comp_name"].split(" - ")
            grade_name = comp_parts[0]

            # Create a unique grade ID that combines type and fixture_id
            composite_grade_id = f"grade_{team_type.lower()}_{fixture_id}"

            grades[fixture_id] = {
                "id": composite_grade_id,
                "fixture_id": fixture_id,
                "comp_id": comp_id,
                "name": grade_name,
                "gender": team["gender"],
                "competition": competitions[comp_id]["name"],
                "competition_ref": db.collection("competitions").document(competitions[comp_id]["id"])
            }

    # Add competitions to Firestore
    for comp_id, comp_data in competitions.items():
        db.collection("competitions").document(comp_data["id"]).set(comp_data)
        print(f"Added competition: {comp_data['name']} with ID {comp_data['id']}")

    # Add grades to Firestore
    for fixture_id, grade_data in grades.items():
        db.collection("grades").document(grade_data["id"]).set(grade_data)
        print(f"Added grade: {grade_data['name']} in {grade_data['competition']}")

def setup_teams(teams_data):
    """Create teams collection using the new composite IDs"""
    print("Setting up teams collection...")

    for team in teams_data:
        fixture_id = team["fixture_id"]
        comp_id = team["comp_id"]
        team_type = team["type"].lower()

        # Create composite IDs for references
        competition_id = f"comp_{team_type}_{comp_id}"
        grade_id = f"grade_{team_type}_{fixture_id}"
        team_id = f"team_{team_type}_{fixture_id}"

        team_data = {
            "id": team_id,
            "name": team["name"],
            "fixture_id": fixture_id,
            "comp_id": comp_id,
            "type": team["type"],
            "gender": team["gender"],
            "club": team["club"],
            "grade_ref": db.collection("grades").document(grade_id),
            "competition_ref": db.collection("competitions").document(competition_id)
        }

        db.collection("teams").document(team_id).set(team_data)
        print(f"Added team: {team['name']} with ID {team_id}")

def setup_sample_games():
    """Create sample games for demonstration with improved references"""
    print("Setting up sample games collection...")

    # Get all teams
    teams_ref = db.collection("teams").stream()
    teams = {doc.id: doc.to_dict() for doc in teams_ref}

    # Get all grades
    grades_ref = db.collection("grades").stream()
    grades = {doc.id: doc.to_dict() for doc in grades_ref}

    # Create 3 sample games for each team
    game_count = 0
    for team_id, team in teams.items():
        team_type = team['type'].lower()
        fixture_id = team['fixture_id']
        grade_id = f"grade_{team_type}_{fixture_id}"
        competition_id = f"comp_{team_type}_{team['comp_id']}"

        for round_num in range(1, 4):
            # Create a unique game ID
            game_id = f"game_{team_type}_{fixture_id}_{round_num}"

            # Generate a game date (Saturdays starting from April 5, 2025)
            game_date = datetime(2025, 4, 5) + timedelta(days=(round_num-1)*7)

            # Random opponent (just using the first team of opposite gender for demo)
            opponent_team = next(
                (t for t_id, t in teams.items() if t['gender'] != team['gender']),
                list(teams.values())[0]  # Fallback to first team
            )

            game_data = {
                "id": game_id,
                "fixture_id": team['fixture_id'],
                "comp_id": team['comp_id'],
                "round": round_num,
                "date": game_date,
                "venue": "Mentone Grammar Playing Fields",
                "home_team": {
                    "id": team_id,
                    "name": team['name'],
                    "score": round_num  # Placeholder score
                },
                "away_team": {
                    "id": opponent_team['id'],
                    "name": opponent_team['name'],
                    "score": round_num - 1  # Placeholder score
                },
                "status": "scheduled",
                "player_stats": {},
                "team_ref": db.collection("teams").document(team_id),
                "grade_ref": db.collection("grades").document(grade_id),
                "competition_ref": db.collection("competitions").document(competition_id)
            }

            db.collection("games").document(game_id).set(game_data)
            game_count += 1

    print(f"Added {game_count} sample games")

def setup_players():
    """Create sample players collection with improved references"""
    print("Setting up players collection...")

    # Get all teams
    teams_ref = db.collection("teams").stream()
    teams = {doc.id: doc.to_dict() for doc in teams_ref}

    # Get all grades
    grades_ref = db.collection("grades").stream()
    grades = {doc.id: doc.to_dict() for doc in grades_ref}

    # Sample player names
    mens_names = ["James Smith", "Michael Brown", "Robert Jones", "David Miller",
                  "John Wilson", "Thomas Moore", "Daniel Taylor", "Paul Anderson",
                  "Andrew Thomas", "Joshua White"]

    womens_names = ["Jennifer Smith", "Lisa Brown", "Mary Jones", "Sarah Miller",
                    "Jessica Wilson", "Emily Moore", "Emma Taylor", "Olivia Anderson",
                    "Isabella Thomas", "Sophia White"]

    # Create players for each team (5 players per team)
    player_count = 0
    for team_id, team in teams.items():
        # Get grade info
        team_type = team['type'].lower()
        fixture_id = team['fixture_id']
        grade_id = f"grade_{team_type}_{fixture_id}"
        grade = grades.get(grade_id, {})

        # Choose names based on gender
        names = mens_names if team['gender'] == "Men" else womens_names

        for i in range(5):
            player_id = f"player_{team_id}_{i+1}"
            grade_name = grade.get('name', 'Unknown Grade')
            player_name = f"{names[i]} ({grade_name})"

            player_data = {
                "id": player_id,
                "name": player_name,
                "teams": [team_id],
                "stats": {
                    "goals": i*2,  # Sample stats
                    "green_cards": i % 3,
                    "yellow_cards": 0 if i < 4 else 1,
                    "red_cards": 0,
                    "appearances": 5
                },
                "gender": team['gender'],
                "primary_team_ref": db.collection("teams").document(team_id),
                "grade_ref": db.collection("grades").document(grade_id)
            }

            db.collection("players").document(player_id).set(player_data)
            player_count += 1

    print(f"Added {player_count} sample players")

def setup_settings():
    """Create settings collection"""
    print("Setting up settings collection...")

    settings_data = {
        "id": "email_settings",
        "pre_game_hours": 24,
        "weekly_summary_day": "Sunday",
        "weekly_summary_time": "20:00",
        "admin_emails": ["admin@mentone.com"]
    }

    db.collection("settings").document("email_settings").set(settings_data)
    print("Added email settings")

if __name__ == "__main__":
    setup_collections()