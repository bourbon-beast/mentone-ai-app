from firebase_functions import https_fn
from firebase_admin import initialize_app

# Initialize Firebase app
initialize_app()

# Import the ladder_api function
from ladder_api import ladder_api

# Export the function
ladder_api = ladder_api