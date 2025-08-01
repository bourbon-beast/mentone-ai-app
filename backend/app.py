"""
FastAPI Application for Mentone Hockey Club Data Pipeline

This application provides REST API endpoints to trigger various 
data pipeline modules for the hockey club dashboard.
"""

import os
import sys
import logging
import asyncio
import subprocess
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import json

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Mentone Hockey Club Pipeline",
    description="REST API to trigger data pipeline modules",
    version="1.0.0"
)

# Request models
class PipelineRequest(BaseModel):
    dry_run: bool = False
    verbose: bool = False
    days: Optional[int] = None
    team_id: Optional[str] = None
    max_games: Optional[int] = None

class MultiModuleRequest(BaseModel):
    modules: list[str]
    dry_run: bool = False
    verbose: bool = False
    days: Optional[int] = None

# Job status tracking (in-memory for now)
job_status = {}

def run_pipeline_module(module_name: str, params: PipelineRequest) -> Dict[str, Any]:
    """Run a specific pipeline module with given parameters."""
    try:
        # Build command arguments
        cmd = [sys.executable, "-m", f"scripts.{module_name}"]

        if params.dry_run:
            cmd.append("--dry-run")
        if params.verbose:
            cmd.append("--verbose")
        if params.days:
            cmd.extend(["--days", str(params.days)])
        if params.team_id:
            cmd.extend(["--team-id", params.team_id])
        if params.max_games:
            cmd.extend(["--max-games", str(params.max_games)])

        # Add credentials if available
        creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if creds_path and os.path.exists(creds_path):
            cmd.extend(["--creds", creds_path])

        logger.info(f"Running command: {' '.join(cmd)}")

        # Run the command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800,  # 30 minutes timeout
            cwd="/app"
        )

        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "command": " ".join(cmd)
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Pipeline module timed out after 30 minutes",
            "returncode": -1
        }
    except Exception as e:
        logger.error(f"Error running pipeline module: {e}")
        return {
            "success": False,
            "error": str(e),
            "returncode": -1
        }

async def run_pipeline_async(job_id: str, module_name: str, params: PipelineRequest):
    """Run pipeline module asynchronously and update job status."""
    job_status[job_id] = {
        "status": "running",
        "started_at": datetime.now().isoformat(),
        "module": module_name,
        "params": params.dict()
    }

    try:
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            run_pipeline_module,
            module_name,
            params
        )

        job_status[job_id].update({
            "status": "completed" if result["success"] else "failed",
            "completed_at": datetime.now().isoformat(),
            "result": result
        })

    except Exception as e:
        job_status[job_id].update({
            "status": "failed",
            "completed_at": datetime.now().isoformat(),
            "error": str(e)
        })

async def run_modules_in_order(job_id: str, modules: list[str], params: PipelineRequest, background_tasks: BackgroundTasks):
    """Helper function to run modules in correct dependency order."""

    # Define execution order - CRITICAL for dependencies!
    execution_order = [
        "competitions",
        "teams",
        "games",
        "results",
        "players",
        "ladder"
    ]

    # Filter and sort requested modules by execution order
    ordered_modules = [m for m in execution_order if m in modules]

    async def run_multi_async():
        job_status[job_id] = {
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "modules": ordered_modules,
            "params": params.dict(),
            "progress": []
        }

        script_map = {
            "competitions": "discover_competitions",
            "teams": "discover_teams",
            "games": "discover_games",
            "results": "update_results",
            "players": "discover_players",
            "ladder": "update_ladder"
        }

        # Run modules sequentially in correct order
        for module in ordered_modules:
            script_name = script_map.get(module, module)

            try:
                logger.info(f"Running module: {module}")
                result = run_pipeline_module(script_name, params)

                success = result["success"]
                job_status[job_id]["progress"].append({
                    "module": module,
                    "completed_at": datetime.now().isoformat(),
                    "success": success,
                    "returncode": result.get("returncode"),
                    "output": result.get("stdout", "")[-500:] if result.get("stdout") else ""
                })

                # STOP if a critical module fails
                if not success and module in ["competitions", "teams"]:
                    logger.error(f"Critical module {module} failed. Stopping pipeline.")
                    job_status[job_id]["status"] = "failed"
                    job_status[job_id]["error"] = f"Critical module {module} failed"
                    return

            except Exception as e:
                logger.error(f"Error in module {module}: {e}")
                job_status[job_id]["progress"].append({
                    "module": module,
                    "completed_at": datetime.now().isoformat(),
                    "success": False,
                    "error": str(e)
                })

                # Stop on critical module failures
                if module in ["competitions", "teams"]:
                    job_status[job_id]["status"] = "failed"
                    return

        # Calculate final status
        successful = sum(1 for p in job_status[job_id]["progress"] if p.get("success", False))
        total = len(ordered_modules)

        job_status[job_id].update({
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
            "successful_modules": successful,
            "total_modules": total,
            "success_rate": f"{successful}/{total}"
        })

    background_tasks.add_task(run_multi_async)
    return {"job_id": job_id, "status": "started", "modules": ordered_modules}

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "mentone-pipeline"
    }

# Convenience endpoints
@app.post("/pipeline/setup")
async def run_setup(request: PipelineRequest, background_tasks: BackgroundTasks):
    """Season setup - competitions and teams foundation."""
    job_id = f"setup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    modules = ["competitions", "teams"]
    return await run_modules_in_order(job_id, modules, request, background_tasks)

@app.post("/pipeline/daily")
async def run_daily_update(request: PipelineRequest, background_tasks: BackgroundTasks):
    """Daily post-game update - results, players, ladder."""
    job_id = f"daily_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    modules = ["results", "players", "ladder"]
    return await run_modules_in_order(job_id, modules, request, background_tasks)

@app.post("/pipeline/weekly")
async def run_weekly_update(request: PipelineRequest, background_tasks: BackgroundTasks):
    """Weekly full refresh - games, results, players, ladder."""
    job_id = f"weekly_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    modules = ["games", "results", "players", "ladder"]
    return await run_modules_in_order(job_id, modules, request, background_tasks)

@app.post("/pipeline/fixtures")
async def run_fixtures_update(request: PipelineRequest, background_tasks: BackgroundTasks):
    """Update fixtures only - for when Hockey Victoria notifies of changes."""
    job_id = f"fixtures_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    modules = ["games"]
    return await run_modules_in_order(job_id, modules, request, background_tasks)

@app.post("/run-pipeline")
async def run_pipeline(request: MultiModuleRequest, background_tasks: BackgroundTasks):
    """Run multiple pipeline modules in sequence - flexible custom combinations."""
    job_id = f"multi_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Convert to PipelineRequest format
    params = PipelineRequest(
        dry_run=request.dry_run,
        verbose=request.verbose,
        days=request.days
    )

    return await run_modules_in_order(job_id, request.modules, params, background_tasks)

@app.get("/pipeline/endpoints")
async def list_endpoints():
    """List all available pipeline endpoints and their purposes."""
    return {
        "convenience_endpoints": {
            "/pipeline/setup": {
                "modules": ["competitions", "teams"],
                "purpose": "Season setup - run once at start of season",
                "frequency": "1-2x per year"
            },
            "/pipeline/daily": {
                "modules": ["results", "players", "ladder"],
                "purpose": "Post-game updates",
                "frequency": "After game days"
            },
            "/pipeline/weekly": {
                "modules": ["games", "results", "players", "ladder"],
                "purpose": "Full refresh of live data",
                "frequency": "Weekly maintenance"
            },
            "/pipeline/fixtures": {
                "modules": ["games"],
                "purpose": "Refresh fixtures when Hockey Victoria notifies changes",
                "frequency": "As needed"
            }
        },
        "flexible_endpoints": {
            "/run-pipeline": {
                "purpose": "Custom module combinations",
                "example": {"modules": ["results", "ladder"], "dry_run": False}
            }
        },
        "individual_endpoints": {
            "/pipeline/competitions": "Individual module endpoints",
            "/pipeline/teams": "Available for specific needs",
            "/pipeline/games": "Direct module access",
            "/pipeline/results": "Granular control",
            "/pipeline/players": "Single module runs",
            "/pipeline/ladder": "Quick updates"
        }
    }

# Individual pipeline endpoints
@app.post("/pipeline/competitions")
async def run_competitions(request: PipelineRequest, background_tasks: BackgroundTasks):
    """Discover competitions and grades."""
    job_id = f"comp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    background_tasks.add_task(run_pipeline_async, job_id, "discover_competitions", request)
    return {"job_id": job_id, "status": "started", "module": "discover_competitions"}

@app.post("/pipeline/teams")
async def run_teams(request: PipelineRequest, background_tasks: BackgroundTasks):
    """Discover teams."""
    job_id = f"teams_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    background_tasks.add_task(run_pipeline_async, job_id, "discover_teams", request)
    return {"job_id": job_id, "status": "started", "module": "discover_teams"}

@app.post("/pipeline/games")
async def run_games(request: PipelineRequest, background_tasks: BackgroundTasks):
    """Discover upcoming games."""
    job_id = f"games_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    background_tasks.add_task(run_pipeline_async, job_id, "discover_games", request)
    return {"job_id": job_id, "status": "started", "module": "discover_games"}

@app.post("/pipeline/results")
async def run_results(request: PipelineRequest, background_tasks: BackgroundTasks):
    """Update game results."""
    job_id = f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    background_tasks.add_task(run_pipeline_async, job_id, "update_results", request)
    return {"job_id": job_id, "status": "started", "module": "update_results"}

@app.post("/pipeline/players")
async def run_players(request: PipelineRequest, background_tasks: BackgroundTasks):
    """Discover player data."""
    job_id = f"players_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    background_tasks.add_task(run_pipeline_async, job_id, "discover_players", request)
    return {"job_id": job_id, "status": "started", "module": "discover_players"}

@app.post("/pipeline/ladder")
async def run_ladder(request: PipelineRequest, background_tasks: BackgroundTasks):
    """Update ladder positions."""
    job_id = f"ladder_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    background_tasks.add_task(run_pipeline_async, job_id, "update_ladder", request)
    return {"job_id": job_id, "status": "started", "module": "update_ladder"}

@app.post("/pipeline/venues")
async def run_venues(request: PipelineRequest, background_tasks: BackgroundTasks):
    """Extract venue information."""
    job_id = f"venues_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    background_tasks.add_task(run_pipeline_async, job_id, "extract_venues", request)
    return {"job_id": job_id, "status": "started", "module": "extract_venues"}

@app.post("/pipeline/full")
async def run_full_pipeline(request: PipelineRequest, background_tasks: BackgroundTasks):
    """Run the complete pipeline in sequence."""
    job_id = f"full_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    async def run_full_async():
        modules = [
            "discover_competitions",
            "discover_teams",
            "discover_games",
            "update_results",
            "discover_players",
            "update_ladder"
        ]

        job_status[job_id] = {
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "module": "full_pipeline",
            "params": request.dict(),
            "progress": []
        }

        for i, module in enumerate(modules):
            try:
                logger.info(f"Running module {i+1}/{len(modules)}: {module}")
                result = run_pipeline_module(module, request)

                job_status[job_id]["progress"].append({
                    "module": module,
                    "completed_at": datetime.now().isoformat(),
                    "success": result["success"],
                    "returncode": result["returncode"]
                })

                if not result["success"]:
                    logger.error(f"Module {module} failed: {result.get('stderr', 'Unknown error')}")
                    # Continue with other modules even if one fails

            except Exception as e:
                logger.error(f"Error in module {module}: {e}")
                job_status[job_id]["progress"].append({
                    "module": module,
                    "completed_at": datetime.now().isoformat(),
                    "success": False,
                    "error": str(e)
                })

        # Determine overall success
        successful_modules = sum(1 for p in job_status[job_id]["progress"] if p.get("success", False))
        total_modules = len(modules)

        job_status[job_id].update({
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
            "successful_modules": successful_modules,
            "total_modules": total_modules,
            "success_rate": f"{successful_modules}/{total_modules}"
        })

    background_tasks.add_task(run_full_async)
    return {"job_id": job_id, "status": "started", "module": "full_pipeline"}

@app.get("/pipeline/status/{job_id}")
async def get_job_status(job_id: str):
    """Get the status of a running job."""
    if job_id not in job_status:
        raise HTTPException(status_code=404, detail="Job not found")

    return job_status[job_id]

@app.get("/pipeline/jobs")
async def list_jobs():
    """List all jobs and their status."""
    return {"jobs": job_status}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)