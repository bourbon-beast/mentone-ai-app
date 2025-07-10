from fastapi import FastAPI
from typing import Optional
import json
from .discover_competitions_cf import discover_competitions_cf
from .discover_teams_cf import discover_teams_cf
from .discover_games_cf import discover_games_cf
from .firebase_functions.https_fn import Request

app = FastAPI()


def call_function(func, params: dict):
    req = Request(method="GET", args=params)
    resp = func(req)
    try:
        return json.loads(resp.data)
    except Exception:
        return {"status": "error", "message": "Failed to parse response"}


@app.post("/api/sync/competitions")
async def sync_competitions(season: Optional[int] = None, dry_run: bool = False):
    params = {}
    if season:
        params["season"] = str(season)
    if dry_run:
        params["dry_run"] = "true"
    return call_function(discover_competitions_cf, params)


@app.post("/api/sync/teams")
async def sync_teams(comp_id: Optional[str] = None, grade_id: Optional[str] = None, dry_run: bool = False):
    params = {}
    if comp_id:
        params["comp_id"] = comp_id
    if grade_id:
        params["grade_id"] = grade_id
    if dry_run:
        params["dry_run"] = "true"
    return call_function(discover_teams_cf, params)


@app.post("/api/sync/games")
async def sync_games(team_id: Optional[str] = None, max_rounds: int = 23, dry_run: bool = False):
    params = {"max_rounds": str(max_rounds)}
    if team_id:
        params["team_id"] = team_id
    if dry_run:
        params["dry_run"] = "true"
    return call_function(discover_games_cf, params)


@app.get("/api/games/upcoming")
async def get_upcoming_games():
    # Placeholder implementation - query Firestore for upcoming games here
    return {"status": "success", "games": []}
