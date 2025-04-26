import json
from datetime import datetime, timedelta # Import timedelta
import firebase_admin
import requests
from bs4 import BeautifulSoup
from firebase_functions import https_fn
from firebase_admin import initialize_app, firestore

# Initialize Firebase safely
try:
    app = firebase_admin.get_app()
except ValueError:
    initialize_app()

# Cache settings
CACHE_TTL_HOURS = 6
CACHE_TTL_SECONDS = CACHE_TTL_HOURS * 3600

# --- CORS Headers ---
# Allow requests from any origin (*) during development.
# For production, replace '*' with your deployed frontend's origin
# (e.g., 'https://your-app-name.web.app') or handle multiple origins.
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS", # Allow GET and preflight OPTIONS requests
    "Access-Control-Allow-Headers": "Content-Type",
}

@https_fn.on_request()
def ladder_api(req: https_fn.Request) -> https_fn.Response:
    """Firebase function to fetch ladder data for a specific competition/fixture."""

    # --- Handle CORS Preflight Requests (OPTIONS method) ---
    # Browsers send an OPTIONS request first to check CORS policy
    if req.method == 'OPTIONS':
        return https_fn.Response("", status=204, headers=CORS_HEADERS)

    # --- Proceed with GET request logic ---
    db = firestore.client()
    comp_id = req.args.get('comp_id')
    fixture_id = req.args.get('fixture_id')

    if not comp_id or not fixture_id:
        return https_fn.Response(
            json.dumps({"error": "Missing comp_id or fixture_id"}),
            status=400,
            content_type="application/json",
            headers=CORS_HEADERS # Add CORS headers to error response
        )

    cache_key = f"{comp_id}_{fixture_id}"
    cache_ref = db.collection("ladder_cache").document(cache_key)
    cache_doc = cache_ref.get()

    if cache_doc.exists:
        cache_data = cache_doc.to_dict()
        cache_timestamp = cache_data.get('timestamp', 0)
        current_time = datetime.now().timestamp()

        if (current_time - cache_timestamp) < CACHE_TTL_SECONDS:
            print(f"[Cache HIT] Serving ladder data for {cache_key}")
            return https_fn.Response(
                json.dumps(cache_data.get('data')),
                content_type="application/json",
                headers=CORS_HEADERS # Add CORS headers to success response
            )
        else:
            print(f"[Cache STALE] Stale data for {cache_key}")
    else:
        print(f"[Cache MISS] No cache for {cache_key}")

    url = f"https://www.hockeyvictoria.org.au/pointscore/{comp_id}/{fixture_id}"
    print(f"[API] Scraping ladder data for fixture {fixture_id} from {url}")

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.select_one('table.table')

        if not table:
            raise ValueError("Ladder table not found on page.")

        rows = table.select('tbody tr')
        found_data = None

        for row in rows:
            cells = row.select('td')
            if len(cells) < 10: continue

            team_cell = cells[0]
            team_link = team_cell.select_one('a')
            team_name = team_link.text.strip() if team_link else team_cell.text.strip()
            position_text = team_cell.text.strip().split('.')[0]

            if "Mentone" in team_name:
                points_text = cells[9].text.strip()
                try:
                    position = int(position_text)
                    points = int(points_text)
                    found_data = {"position": position, "points": points}
                    print(f"[API] Found Mentone data for {fixture_id}: Pos={position}, Pts={points}")
                    break
                except ValueError:
                    print(f"[API] Could not parse position/points for {team_name} in fixture {fixture_id}")
                    found_data = {"position": None, "points": None, "error": "Parsing Error"}
                    break

        # Store result in cache
        if found_data:
            cache_ref.set({
                "data": found_data,
                "timestamp": datetime.now().timestamp(),
                "comp_id": comp_id,
                "fixture_id": fixture_id
            })

            # Update team document (consider if this should be less frequent)
            if "error" not in found_data:
                try:
                    # Use integer comparison if fixture_id in Firestore is stored as int
                    fixture_id_int = int(fixture_id)
                    teams_ref = db.collection("teams")
                    # Query using the INT version of fixture_id
                    team_query = teams_ref.where("fixture_id", "==", fixture_id_int) \
                        .where("is_home_club", "==", True) \
                        .limit(1) # Query only Mentone teams
                    team_docs = list(team_query.stream()) # Use stream() for potential iteration

                    if team_docs:
                        team_doc = team_docs[0] # Get the first match
                        team_ref = teams_ref.document(team_doc.id)
                        team_ref.update({
                            "ladder_position": found_data["position"],
                            "ladder_points": found_data["points"],
                            "ladder_updated_at": firestore.SERVER_TIMESTAMP
                        })
                        print(f"[API] Updated team {team_doc.id} with ladder position {found_data['position']}")
                    else:
                        print(f"[API] No matching Mentone team found for fixture_id {fixture_id_int} to update ladder pos.")

                except ValueError:
                    print(f"[API] Invalid fixture_id format: {fixture_id}. Cannot query/update team.")
                except Exception as update_err:
                    print(f"[API] Error updating team document for fixture {fixture_id}: {update_err}")


            return https_fn.Response(
                json.dumps(found_data),
                content_type="application/json",
                headers=CORS_HEADERS # Add CORS headers
            )
        else:
            not_found_data = {"position": None, "points": None, "error": "Team Not Found"}
            cache_ref.set({
                "data": not_found_data,
                "timestamp": datetime.now().timestamp(),
                "comp_id": comp_id,
                "fixture_id": fixture_id
            })
            return https_fn.Response(
                json.dumps(not_found_data),
                status=404,
                content_type="application/json",
                headers=CORS_HEADERS # Add CORS headers
            )

    except ValueError as e:
        error_msg = str(e)
        print(f"[API] Value error scraping ladder for fixture {fixture_id}: {error_msg}")
        status_code = 404 if "Ladder table not found" in error_msg else 500
        return https_fn.Response(
            json.dumps({"error": error_msg}), status=status_code, content_type="application/json", headers=CORS_HEADERS # Add CORS headers
        )

    except requests.RequestException as e:
        error_msg = str(e)
        print(f"[API] Request error scraping ladder for fixture {fixture_id}: {error_msg}")
        status_code = 404 if getattr(e, 'response', None) and e.response.status_code == 404 else 500
        return https_fn.Response(
            json.dumps({"error": error_msg}), status=status_code, content_type="application/json", headers=CORS_HEADERS # Add CORS headers
        )
    except Exception as e: # Generic fallback
        error_msg = f"An unexpected error occurred: {str(e)}"
        print(f"[API] Unexpected error for fixture {fixture_id}: {error_msg}")
        return https_fn.Response(
            json.dumps({"error": error_msg}), status=500, content_type="application/json", headers=CORS_HEADERS # Add CORS headers
        )

# --- Ensure your main.py or equivalent exports the function correctly ---
# (The export part you provided seems correct if this code is in ladder_api.py
# and your main.py imports and exports it)