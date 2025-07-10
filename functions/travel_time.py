import json
import os
import logging
import requests

import firebase_admin
from firebase_admin import initialize_app, firestore
from firebase_functions import https_fn

# Initialize Firebase
try:
    firebase_admin.get_app()
except ValueError:
    initialize_app()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



# Google Maps API key - Set this using environment variables or Firebase config
# GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY')
GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY')

@https_fn.on_request()
def calculate_travel_time(req: https_fn.Request) -> https_fn.Response:
    """
    HTTP Cloud Function that calculates travel time between two venues
    using Google Maps Distance Matrix API.

    Args:
        req: The incoming HTTP request

    Returns:
        JSON response with travel details
    """
    # Initialize Firestore
    db = firestore.client()

    # Set CORS headers for preflight requests
    if req.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return https_fn.Response('', status=204, headers=headers)

    # Set CORS headers for the main request
    headers = {'Access-Control-Allow-Origin': '*'}

    # Get the API key
    api_key = GOOGLE_MAPS_API_KEY
    if not api_key:
        logger.error("Google Maps API key not configured")
        return https_fn.Response(
            json.dumps({'error': 'API key not configured'}),
            status=500,
            mimetype='application/json',
            headers=headers
        )

    # Parse request
    try:
    request_json = req.get_json(silent=True)

        if request_json:
            # JSON request
            origin = request_json.get('origin')
            destination = request_json.get('destination')
            mode = request_json.get('mode', 'driving')
            units = request_json.get('units', 'metric')
        else:
            # Query parameters
            origin = req.args.get('origin')
            destination = req.args.get('destination')
            mode = req.args.get('mode', 'driving')
            units = req.args.get('units', 'metric')

            # Special handling for venue IDs/codes instead of addresses
            origin_venue_id = req.args.get('origin_venue_id')
            if origin_venue_id and not origin:
                origin = get_venue_address(origin_venue_id)

            destination_venue_id = req.args.get('destination_venue_id')
            if destination_venue_id and not destination:
                destination = get_venue_address(destination_venue_id)

        # Validate required parameters
        if not origin or not destination:
            return https_fn.Response(
                json.dumps({'error': 'Origin and destination are required'}),
                status=400,
                mimetype='application/json',
                headers=headers
            )

        # Add Victoria, Australia if not included
        if 'australia' not in origin.lower() and 'vic' not in origin.lower():
            origin = f"{origin}, Victoria, Australia"

        if 'australia' not in destination.lower() and 'vic' not in destination.lower():
            destination = f"{destination}, Victoria, Australia"

        # Make request to Google Maps Distance Matrix API
        url = 'https://maps.googleapis.com/maps/api/distancematrix/json'
        params = {
            'origins': origin,
            'destinations': destination,
            'mode': mode,
            'units': units,
            'key': api_key
        }

        logger.info(f"Making request to Google Maps API with params: {params}")
        response = requests.get(url, params=params)
        data = response.json()

        # Handle API error responses
        if data.get('status') != 'OK':
            logger.error(f"Google Maps API error: {data.get('status')}")
            return https_fn.Response(
                json.dumps({
                    'error': f"Google Maps API error: {data.get('status')}",
                    'details': data.get('error_message', 'No details available')
                }),
                status=500,
                mimetype='application/json',
                headers=headers
            )

        # Process results
        try:
            elements = data['rows'][0]['elements'][0]

            if elements['status'] != 'OK':
                return https_fn.Response(
                    json.dumps({'error': f"Route calculation error: {elements['status']}"}),
                    status=400,
                    mimetype='application/json',
                    headers=headers
                )

            # Return travel information
            result = {
                'distance': {
                    'text': elements['distance']['text'],
                    'value': elements['distance']['value']  # in meters
                },
                'duration': {
                    'text': elements['duration']['text'],
                    'value': elements['duration']['value']  # in seconds
                },
                'origin': data['origin_addresses'][0],
                'destination': data['destination_addresses'][0]
            }

            # Cache the result in Firestore for future use
            cache_travel_data(origin, destination, result)

            return https_fn.Response(
                json.dumps(result),
                status=200,
                mimetype='application/json',
                headers=headers
            )

        except (KeyError, IndexError) as e:
            logger.error(f"Error parsing Google Maps API response: {str(e)}")
            return https_fn.Response(
                json.dumps({'error': 'Error parsing API response', 'details': str(e)}),
                status=500,
                mimetype='application/json',
                headers=headers
            )

    except Exception as e:
        logger.exception("Error calculating travel time")
        return https_fn.Response(
            json.dumps({'error': str(e)}),
            status=500,
            mimetype='application/json',
            headers=headers
        )

def get_venue_address(venue_id):
    """
    Get venue address from Firestore.

    Args:
        venue_id: Venue ID or code

    Returns:
        str: Venue address or None if not found
    """
    try:
        # Try direct lookup by ID first
        venue_ref = db.collection('venues').document(venue_id)
        venue = venue_ref.get()

        if venue.exists:
            venue_data = venue.to_dict()
            if venue_data.get('address'):
                return venue_data['address']
            elif venue_data.get('name'):
                return venue_data['name']

        # If direct lookup fails, try querying by name
        query = db.collection('venues').where('name', '==', venue_id).limit(1)
        venues = list(query.stream())

        if venues:
            venue_data = venues[0].to_dict()
            if venue_data.get('address'):
                return venue_data['address']
            elif venue_data.get('name'):
                return venue_data['name']

        # If all else fails, return the ID as-is
        return venue_id

    except Exception as e:
        logger.error(f"Error getting venue address: {str(e)}")
        return venue_id

def cache_travel_data(origin, destination, result):
    """
    Cache travel data in Firestore.

    Args:
        origin: Origin address
        destination: Destination address
        result: Travel data result
    """
    try:
        # Create a cache key from origin and destination
        # Simplify addresses to reduce variations
        origin_simple = simplify_address(origin)
        dest_simple = simplify_address(destination)

        cache_key = f"{origin_simple}_to_{dest_simple}"

        # Add timestamp
        result['timestamp'] = firestore.SERVER_TIMESTAMP

        # Store in Firestore
        cache_ref = db.collection('travel_cache').document(cache_key)
        cache_ref.set({
            'origin': origin,
            'destination': destination,
            'origin_simple': origin_simple,
            'destination_simple': dest_simple,
            'result': result,
            'timestamp': firestore.SERVER_TIMESTAMP
        })

    except Exception as e:
        logger.error(f"Error caching travel data: {str(e)}")

def simplify_address(address):
    """
    Simplify address for cache key.

    Args:
        address: Address string

    Returns:
        str: Simplified address for cache key
    """
    # Convert to lowercase
    address = address.lower()

    # Remove common words and punctuation
    for word in ['victoria', 'australia', 'vic', 'road', 'street', 'avenue', 'drive']:
        address = address.replace(word, '')

    # Remove all non-alphanumeric characters
    address = ''.join(char for char in address if char.isalnum() or char.isspace())

    # Replace multiple spaces with a single space
    address = ' '.join(address.split())

    # Remove all spaces
    address = address.replace(' ', '')

    return address
