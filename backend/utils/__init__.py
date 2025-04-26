# Exposes the most useful functions from all utility modules
# Makes imports cleaner in the script files

# Import common utilities for easier access from outside the package
from .firebase_init import initialize_firebase
from .request_utils import make_request, build_url, create_session
from .logging_utils import setup_logger, get_log_level_from_string
from .parsing_utils import (
    clean_text,
    extract_number,
    parse_date,
    extract_competition_id,
    extract_fixture_id,
    is_mentone_team,
    extract_table_data,
    save_debug_html,
    extract_json_from_script
)