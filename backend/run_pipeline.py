#!/usr/bin/env python3
"""
Hockey Victoria Data Pipeline Orchestrator

This script orchestrates the execution of various data pipeline modules
for the Mentone Hockey Club dashboard.

Usage:
    python -m backend.run_pipeline [--modules MODULE1,MODULE2,...] [--dry-run] [--creds CREDS_PATH] [--verbose]

Modules:
    competitions - Discover competitions and grades
    teams        - Discover teams for each grade
    games        - Discover games/fixtures
    results      - Update game results
    players      - Discover player information
    ladder       - Update ladder positions
    all          - Run all modules in order

Examples:
    # Run all modules
    python -m backend.run_pipeline --modules all

    # Run only competitions and teams modules
    python -m backend.run_pipeline --modules competitions,teams

    # Run in dry-run mode (no database writes)
    python -m backend.run_pipeline --modules all --dry-run
"""

import argparse
import sys
import importlib
import time
from datetime import datetime

# Import utility modules
from backend.utils.logging_utils import setup_logger

# Define available modules in execution order
AVAILABLE_MODULES = [
    "competitions",  # Discover competitions and grades
    "teams",         # Discover teams
    "games",         # Discover upcoming games
    "results",       # Update game results
    "players",       # Discover player data
    "ladder"         # Update ladder positions
]

def run_module(module_name, args, logger):
    """Run a specific pipeline module.

    Args:
        module_name: Name of the module to run
        args: Command line arguments
        logger: Logger instance

    Returns:
        bool: Success status
    """
    try:
        logger.info(f"Starting module: {module_name}")
        module_start_time = datetime.now()

        # Import the module dynamically
        module_path = f"backend.scripts.discover_{module_name}"
        if module_name == "results":
            module_path = "backend.scripts.update_results"
        elif module_name == "ladder":
            module_path = "backend.scripts.update_ladder"

        module = importlib.import_module(module_path)

        # Prepare arguments for the module
        module_args = []
        if args.dry_run:
            module_args.append("--dry-run")
        if args.creds:
            module_args.extend(["--creds", args.creds])
        if args.verbose:
            module_args.append("--verbose")

        # Use module-specific arguments if defined in args_map
        if hasattr(args, "args_map") and module_name in args.args_map:
            module_args.extend(args.args_map[module_name])

        # Convert arguments to sys.argv format
        module_argv = [f"python -m {module_path}"] + module_args

        # Backup original sys.argv
        original_argv = sys.argv
        sys.argv = module_argv

        # Run the module's main function
        result = module.main()

        # Restore original sys.argv
        sys.argv = original_argv

        elapsed_time = (datetime.now() - module_start_time).total_seconds()

        if result == 0:
            logger.info(f"Module {module_name} completed successfully in {elapsed_time:.2f} seconds")
            return True
        else:
            logger.error(f"Module {module_name} failed with exit code {result}")
            return False

    except ImportError as e:
        logger.error(f"Failed to import module {module_name}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error running module {module_name}: {e}")
        return False

def main():
    """Main entry point for the pipeline orchestrator."""
    parser = argparse.ArgumentParser(
        description="Run Hockey Victoria data pipeline modules")

    parser.add_argument(
        "--modules",
        type=str,
        default="all",
        help="Comma-separated list of modules to run (competitions,teams,games,results,players,ladder,all)"
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

    # Module-specific arguments (advanced usage)
    parser.add_argument(
        "--args",
        type=str,
        help="JSON-formatted string with module-specific arguments, e.g.: '{\"games\":[\"--days\",\"7\"],\"results\":[\"--days\",\"3\"]}'"
    )

    args = parser.parse_args()

    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    logger = setup_logger("pipeline", log_level=log_level)

    # Parse module-specific arguments if provided
    if args.args:
        import json
        try:
            args.args_map = json.loads(args.args)
            logger.debug(f"Parsed module-specific arguments: {args.args_map}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse --args JSON: {e}")
            return 1

    # Determine which modules to run
    modules_to_run = []
    if args.modules.lower() == "all":
        modules_to_run = AVAILABLE_MODULES
    else:
        requested_modules = [m.strip().lower() for m in args.modules.split(",")]
        for module in requested_modules:
            if module in AVAILABLE_MODULES:
                modules_to_run.append(module)
            else:
                logger.warning(f"Unknown module: {module}")

    if not modules_to_run:
        logger.error("No valid modules specified")
        return 1

    # Start the pipeline
    logger.info(f"Starting Hockey Victoria data pipeline with modules: {', '.join(modules_to_run)}")
    pipeline_start_time = datetime.now()

    successful_modules = 0
    failed_modules = 0

    for module in modules_to_run:
        success = run_module(module, args, logger)
        if success:
            successful_modules += 1
        else:
            failed_modules += 1

        # Short pause between modules
        time.sleep(1)

    # Report results
    pipeline_elapsed_time = (datetime.now() - pipeline_start_time).total_seconds()
    logger.info(f"Pipeline completed in {pipeline_elapsed_time:.2f} seconds")
    logger.info(f"Modules: {successful_modules} successful, {failed_modules} failed")

    if args.dry_run:
        logger.info("DRY RUN - No database changes were made")

    if failed_modules > 0:
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())