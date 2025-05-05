#!/usr/bin/env python3
"""
Hockey Victoria Data Pipeline Orchestrator - Interactive Mode

This script orchestrates the execution of various data pipeline modules
for the Mentone Hockey Club dashboard in an interactive mode.

Usage:
    python -m backend.run_pipeline

The script will prompt you for which modules to run and configuration options.
"""

import sys
import importlib
import time
import os
import json
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

# Default credentials location - adjust as needed
DEFAULT_CREDS_PATHS = [
    "backend/secrets/serviceAccountKey.json",
    "serviceAccountKey.json",
    os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
]

def find_credentials():
    """Attempt to find credential file in common locations"""
    for path in DEFAULT_CREDS_PATHS:
        if path and os.path.exists(path):
            return path
    return None

def run_module(module_name, config, logger):
    """Run a specific pipeline module.

    Args:
        module_name: Name of the module to run
        config: Configuration dictionary
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
        if config.get("dry_run"):
            module_args.append("--dry-run")
        if config.get("creds_path"):
            module_args.extend(["--creds", config["creds_path"]])
        if config.get("verbose"):
            module_args.append("--verbose")

        # Add module-specific arguments
        if module_name in config.get("module_args", {}):
            module_args.extend(config["module_args"][module_name])

        # Convert arguments to sys.argv format
        module_argv = [module_path]  # Just use the module path as the script name
        module_argv.extend(module_args)  # Add the arguments

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

def print_header():
    """Print a nice header for the interactive mode"""
    print("\n" + "=" * 80)
    print("=" * 30 + " HOCKEY VICTORIA DATA PIPELINE " + "=" * 29)
    print("=" * 80)
    print("\nMentone Hockey Club Data Pipeline - Interactive Mode\n")

def get_modules_selection():
    """Prompt user to select modules to run"""
    print("\nAvailable modules:")
    for i, module in enumerate(AVAILABLE_MODULES, 1):
        print(f"  {i}. {module}")
    print("  A. All modules")
    print("  Q. Quit\n")

    while True:
        selection = input("Enter your selection (comma-separated numbers, 'A' for all, or 'Q' to quit): ").strip().upper()

        if selection == 'Q':
            return None

        if selection == 'A':
            return AVAILABLE_MODULES

        try:
            # Try to parse as comma-separated numbers
            numbers = [int(n.strip()) for n in selection.split(',') if n.strip()]
            selected_modules = []
            for num in numbers:
                if 1 <= num <= len(AVAILABLE_MODULES):
                    selected_modules.append(AVAILABLE_MODULES[num-1])
                else:
                    print(f"Invalid selection: {num}. Please choose between 1 and {len(AVAILABLE_MODULES)}.")
                    break
            else:
                if selected_modules:
                    return selected_modules
        except ValueError:
            pass

        print("Invalid selection. Please try again.")

def get_credentials_path():
    """Prompt user for credentials path"""
    default_path = find_credentials()
    default_prompt = f" (press Enter for {default_path})" if default_path else ""

    print("\nFirebase Credentials:")
    print("  The script needs Firebase credentials to access the database.")

    while True:
        path = input(f"Enter path to serviceAccountKey.json{default_prompt}: ").strip()

        # Use default if just pressing Enter
        if not path and default_path:
            return default_path

        # Check if file exists
        if path and os.path.exists(path):
            return path
        elif path:
            print(f"File not found: {path}")
            try_again = input("Try again? (Y/n): ").strip().lower()
            if try_again == 'n':
                return None
        else:
            print("No credentials provided.")
            use_dry_run = input("Would you like to run in dry-run mode instead? (Y/n): ").strip().lower()
            if use_dry_run != 'n':
                return None

def get_dry_run_preference():
    """Prompt user for dry-run preference"""
    print("\nDry Run Mode:")
    print("  In dry-run mode, no changes will be made to the database.")

    while True:
        response = input("Run in dry-run mode? (y/N): ").strip().lower()
        if response in ('y', 'yes'):
            return True
        elif response in ('', 'n', 'no'):
            return False
        else:
            print("Invalid input. Please enter 'y' or 'n'.")

def get_verbose_preference():
    """Prompt user for verbose logging preference"""
    print("\nVerbose Logging:")
    print("  Verbose mode provides more detailed logs.")

    while True:
        response = input("Enable verbose logging? (y/N): ").strip().lower()
        if response in ('y', 'yes'):
            return True
        elif response in ('', 'n', 'no'):
            return False
        else:
            print("Invalid input. Please enter 'y' or 'n'.")

def get_module_days(module_name):
    """Prompt user for number of days for certain modules"""
    if module_name in ('games', 'results'):
        print(f"\nDays ahead for {module_name}:")
        default_days = 14 if module_name == 'games' else 7

        while True:
            try:
                days_input = input(f"Enter number of days to look {module_name} (default: {default_days}): ").strip()
                if not days_input:
                    return default_days
                days = int(days_input)
                if days > 0:
                    return days
                else:
                    print("Please enter a positive number.")
            except ValueError:
                print("Invalid input. Please enter a number.")

    return None

def main():
    """Main entry point for the interactive pipeline orchestrator."""
    print_header()

    # Setup logging
    logger = setup_logger("pipeline")

    # Get module selection
    selected_modules = get_modules_selection()
    if not selected_modules:
        print("Exiting.")
        return 0

    # Get configuration options
    config = {
        "dry_run": False,
        "verbose": False,
        "creds_path": None,
        "module_args": {}
    }

    # Get credentials path
    config["creds_path"] = get_credentials_path()

    # If no credentials, suggest dry run
    if not config["creds_path"]:
        config["dry_run"] = True
        print("No credentials provided. Running in dry-run mode.")
    else:
        # Otherwise ask about dry run
        config["dry_run"] = get_dry_run_preference()

    # Get verbose preference
    config["verbose"] = get_verbose_preference()

    # Get module-specific days parameter
    for module in selected_modules:
        days = get_module_days(module)
        if days:
            config["module_args"][module] = ["--days", str(days)]

    # Show configuration summary
    print("\nConfiguration Summary:")
    print(f"  Modules: {', '.join(selected_modules)}")
    print(f"  Dry Run: {'Yes' if config['dry_run'] else 'No'}")
    print(f"  Verbose: {'Yes' if config['verbose'] else 'No'}")
    print(f"  Credentials: {config['creds_path'] or 'None (dry-run)'}")
    for module, args in config.get("module_args", {}).items():
        print(f"  {module.capitalize()} args: {' '.join(args)}")

    # Confirm execution
    print("\nReady to execute pipeline.")
    confirm = input("Continue? (Y/n): ").strip().lower()
    if confirm in ('n', 'no'):
        print("Execution cancelled.")
        return 0

    # Start the pipeline
    print("\nStarting pipeline...")
    pipeline_start_time = datetime.now()

    # Configure logging level based on verbose setting
    log_level = "DEBUG" if config["verbose"] else "INFO"
    logger = setup_logger("pipeline", log_level=log_level)

    logger.info(f"Starting Hockey Victoria data pipeline with modules: {', '.join(selected_modules)}")

    successful_modules = 0
    failed_modules = 0

    for module in selected_modules:
        success = run_module(module, config, logger)
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

    print("\nPipeline Execution Complete:")
    print(f"  Duration: {pipeline_elapsed_time:.2f} seconds")
    print(f"  Successful: {successful_modules}/{len(selected_modules)}")
    print(f"  Failed: {failed_modules}/{len(selected_modules)}")

    if config["dry_run"]:
        logger.info("DRY RUN - No database changes were made")
        print("  Note: No database changes were made (dry-run mode)")

    if failed_modules > 0:
        print("\nSome modules failed. Check the logs for details.")
        return 1

    print("\nAll modules completed successfully!")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(130)