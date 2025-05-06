from firebase_functions import https_fn
from firebase_admin import initialize_app

# Initialize Firebase
initialize_app()

# Import functions
from ladder_api import ladder_api
from travel_time import calculate_travel_time  # Add this import

# Export functions
ladder_api = ladder_api
calculate_travel_time = calculate_travel_time  # Add this export