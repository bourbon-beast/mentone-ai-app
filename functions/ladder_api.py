import json
import time
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from firebase_functions import https_fn
from firebase_admin import initialize_app, firestore

# Initialize Firebase
initialize_app()
db = firestore.client()

# Cache settings
CACHE_TTL_HOURS = 6

@https_fn.on_request()
def ladder_api(req: https_fn.Request) -> https_fn.Response:
    """Firebase function to fetch ladder data for a specific competition/fixture."""

    # Extract query parameters
    comp_id = req.args.get('comp_id')
    fixture_id = req.args.get('fixture_id')

    if not comp_id or not fixture_id:
        return https_fn.Response(
            json.dumps({"error": "Missing comp_id or fixture_id"}),
            status=400,
            content_type="application/json"
        )

    cache_key = f"{comp_id}_{fixture_id}"

    # Check if we have cached data in Firestore
    cache_ref = db.collection("ladder_cache").document(cache_key)
    cache_doc = cache_ref.get()

    if cache_doc.exists:
        cache_data = cache_doc.to_dict()
        cache_timestamp = cache_data.get('timestamp', 0)
        current_time = datetime.now().timestamp()

        # Check if cache is still valid
        if (current_time - cache_timestamp) < (CACHE_TTL_HOURS * 3600):
            print(f"[Cache HIT] Serving ladder data for {cache_key}")
            return https_fn.Response(
                json.dumps(cache_data.get('data')),
                content_type="application/json"
            )
        else:
            print(f"[Cache STALE] Stale data for {cache_key}")
    else:
        print(f"[Cache MISS] No cache for {cache_key}")

    # Scrape the ladder data
    url = f"https://www.hockeyvictoria.org.au/pointscore/{comp_id}/{fixture_id}"
    print(f"[API] Scraping ladder data for fixture {fixture_id} from {url}")

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()  # Raise exception for HTTP errors

        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.select_one('table.table')

        if not table:
            raise ValueError("Ladder table not found on page.")

        rows = table.select('tbody tr')
        found_data = None

        for row in rows:
            cells = row.select('td')
            if len(cells) < 10:
                continue  # Need at least 10 columns

            team_cell = cells[0]
            team_link = team_cell.select_one('a')

            if team_link:
                team_name = team_link.text.strip()
            else:
                team_name = team_cell.text.strip()

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

        # Store result in Firestore cache
        if found_data:
            cache_ref.set({
                "data": found_data,
                "timestamp": datetime.now().timestamp(),
                "comp_id": comp_id,
                "fixture_id": fixture_id
            })

            # Also update the team document with latest ladder position
            if "error" not in found_data:
                teams_ref = db.collection("teams")
                team_query = teams_ref.where("fixture_id", "==", int(fixture_id)).where("club", "==", "Mentone").limit(1)
                team_docs = team_query.get()

                for team_doc in team_docs:
                    team_ref = teams_ref.document(team_doc.id)
                    team_ref.update({
                        "ladder_position": found_data["position"],
                        "ladder_points": found_data["points"],
                        "ladder_updated_at": firestore.SERVER_TIMESTAMP
                    })
                    print(f"[API] Updated team {team_doc.id} with ladder position {found_data['position']}")

            return https_fn.Response(
                json.dumps(found_data),
                content_type="application/json"
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
                content_type="application/json"
            )

    except ValueError as e:
        error_msg = str(e)
        print(f"[API] Error scraping ladder for fixture {fixture_id}: {error_msg}")

        if "Ladder table not found" in error_msg:
            status_code = 404
        else:
            status_code = 500

        return https_fn.Response(
            json.dumps({"error": error_msg}),
            status=status_code,
            content_type="application/json"
        )

    except requests.RequestException as e:
        error_msg = str(e)
        print(f"[API] Request error scraping ladder for fixture {fixture_id}: {error_msg}")

        status_code = 404 if getattr(e, 'response', None) and e.response.status_code == 404 else 500

        return https_fn.Response(
            json.dumps({"error": error_msg}),
            status=status_code,
            content_type="application/json"
        )