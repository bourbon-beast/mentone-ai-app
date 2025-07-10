"""
Cloud Function to extract Hockey Victoria venue information from game pages.
"""
import json
import re
import time
from datetime import datetime
from urllib.parse import urljoin, unquote

import firebase_admin
import requests
import pytz 
from bs4 import BeautifulSoup
from firebase_functions import https_fn
from firebase_admin import initialize_app, firestore

# --- Global Variables & Constants ---
try:
    firebase_admin.get_app()
except ValueError:
    initialize_app()

BASE_URL = "https://www.hockeyvictoria.org.au"
DELAY_BETWEEN_REQUESTS_CF = 0.25  # seconds
AUSTRALIA_TZ = pytz.timezone("Australia/Melbourne")

# --- CORS Headers ---
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

# --- Logging Setup (Simplified) ---
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- Utility Functions (Adapted or Inlined) ---
def make_request_cf(url, session=None, timeout=10):
    requester = session if session else requests.Session()
    try:
        response = requester.get(url, timeout=timeout)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for {url}: {e}")
        return None

def clean_text_cf(text):
    if text is None: return ""
    return text.strip().replace('\n', ' ').replace('\r', ' ')

# --- Core Logic Functions (from extract_venues.py, adapted for CF) ---

def extract_venue_info_cf(soup, game_url=""):
    """Extracts venue information from a parsed game page (BeautifulSoup object)."""
    venue_data = {}

    # Try to find "Venue" div and its content
    venue_label_div = soup.find('div', string=lambda t: t and t.strip().lower() == 'venue')
    if venue_label_div and venue_label_div.parent:
        # Attempt to get text sibling or parent's direct text
        venue_name_candidate = ""
        for elem in venue_label_div.next_siblings:
            if isinstance(elem, str) and elem.strip():
                venue_name_candidate = elem.strip()
                break
        if not venue_name_candidate: # Fallback to parent's text if direct sibling not found
             all_text_in_parent = venue_label_div.parent.get_text(separator='|', strip=True)
             parts = [p.strip() for p in all_text_in_parent.split('|')]
             try:
                 venue_idx = parts.index('Venue') # Case-sensitive might be an issue
                 if venue_idx + 1 < len(parts) and parts[venue_idx+1] not in ['Field', 'Address']: # Basic check
                     venue_name_candidate = parts[venue_idx+1]
             except ValueError:
                 pass # 'Venue' not found as expected

        if venue_name_candidate:
            venue_data['name'] = clean_text_cf(venue_name_candidate)
        
        # Address is often in a 'font-size-sm' div following the venue section
        address_div = venue_label_div.parent.find_next_sibling('div', class_='font-size-sm')
        if not address_div: # If not sibling, try as child of sibling
            parent_sibling = venue_label_div.parent.find_next_sibling('div')
            if parent_sibling: address_div = parent_sibling.find('div', class_='font-size-sm')
        if address_div:
            venue_data['address'] = clean_text_cf(address_div.get_text(separator=", ", strip=True))

    # Try to find "Field" information
    field_label_div = soup.find('div', string=lambda t: t and t.strip().lower() == 'field')
    if field_label_div and field_label_div.parent:
        field_code_candidate = ""
        for elem in field_label_div.next_siblings:
            if isinstance(elem, str) and elem.strip():
                field_code_candidate = elem.strip()
                break
        if field_code_candidate:
             venue_data['field_code'] = clean_text_cf(field_code_candidate)


    # Extract map URL
    map_iframe_tag = soup.select_one('iframe[src*="maps.google.com/maps"]')
    if map_iframe_tag:
        map_url_raw = map_iframe_tag.get('src')
        if map_url_raw:
            venue_data['map_url'] = map_url_raw
            query_match = re.search(r"[?&]q=([^&]+)", map_url_raw)
            if query_match:
                try:
                    venue_data['google_maps_query'] = unquote(query_match.group(1))
                except Exception: # Sometime unquote fails on odd chars
                    venue_data['google_maps_query'] = query_match.group(1)


    if venue_data.get('name'):
        # Generate a more robust venue_code
        # Use parts of name and address if available to make it more unique
        code_base = venue_data['name']
        if venue_data.get('address'): # Add first part of address for uniqueness
            code_base += "_" + venue_data['address'].split(',')[0]
        
        venue_code_generated = re.sub(r'[^A-Z0-9_]', '', code_base.upper(), flags=re.IGNORECASE)
        venue_code_generated = re.sub(r'_+', '_', venue_code_generated).strip('_')
        venue_data['id'] = venue_code_generated[:50] # Firestore ID limit is higher, but keep it reasonable
        
        venue_data['source_game_url'] = game_url # Track where it was found
        venue_data['updated_at'] = datetime.now(AUSTRALIA_TZ).astimezone(pytz.utc)
        # created_at will be handled by save function
        return venue_data
    
    logger.debug(f"No sufficient venue data extracted from {game_url}. Found: {venue_data}")
    return None


def save_venue_cf(db_client, venue_data_obj, dry_run_mode):
    """Saves venue data to Firestore. Uses generated 'id' field as document ID."""
    if not venue_data_obj.get('id') or not venue_data_obj.get('name'):
        logger.error(f"Venue data missing 'id' or 'name': {venue_data_obj}")
        return False, "missing_id_or_name"

    venue_doc_id = venue_data_obj['id']
    venue_ref = db_client.collection("venues").document(venue_doc_id)

    if dry_run_mode:
        logger.info(f"[DRY RUN] Would save venue: {venue_data_obj.get('name')} (ID: {venue_doc_id})")
        return True, "dry_run"
    
    try:
        now_utc = datetime.now(AUSTRALIA_TZ).astimezone(pytz.utc)
        venue_data_obj["updated_at"] = now_utc
        
        existing_doc = venue_ref.get()
        if existing_doc.exists:
            venue_data_obj["created_at"] = existing_doc.to_dict().get("created_at", now_utc)
            # Optionally merge specific fields if needed, e.g. source_game_urls list
            existing_sources = existing_doc.to_dict().get("source_game_urls", [])
            if isinstance(existing_sources, list):
                 if venue_data_obj["source_game_url"] not in existing_sources:
                    existing_sources.append(venue_data_obj["source_game_url"])
                 venue_data_obj["source_game_urls"] = existing_sources
            else: # if existing field is not a list (e.g. single string)
                venue_data_obj["source_game_urls"] = list(set([existing_sources, venue_data_obj["source_game_url"]]))

        else:
            venue_data_obj["created_at"] = now_utc
            venue_data_obj["source_game_urls"] = [venue_data_obj["source_game_url"]]
        
        # Remove single source_game_url if list exists
        if "source_game_url" in venue_data_obj and "source_game_urls" in venue_data_obj:
            del venue_data_obj["source_game_url"]

        venue_ref.set(venue_data_obj, merge=True)
        logger.debug(f"Venue {venue_data_obj.get('name')} (ID: {venue_doc_id}) saved.")
        return True, "saved"
    except Exception as e_save:
        logger.error(f"Failed to save venue {venue_data_obj.get('name')} (ID: {venue_doc_id}): {e_save}", exc_info=True)
        return False, "error"

# --- Cloud Function Entry Point ---
@https_fn.on_request()
def extract_venues_cf(req: https_fn.Request) -> https_fn.Response:
    if req.method == 'OPTIONS':
        return https_fn.Response("", status=204, headers=CORS_HEADERS)

    log_level_param = req.args.get("log_level", "INFO").upper()
    logger.setLevel(getattr(logging, log_level_param, logging.INFO))
    logger.info(f"extract_venues_cf triggered. Log level: {log_level_param}")

    db = firestore.client()
    session = requests.Session()

    # Request Parameters
    single_game_url_param = req.args.get("game_url")
    process_from_firestore_param = req.args.get("process_from_firestore", "false").lower() == "true"
    limit_firestore_games_param = req.args.get("limit_games", type=int, default=10) # Default limit for firestore processing
    dry_run_param = req.args.get("dry_run", "false").lower() == "true"
    # update_missing_param = req.args.get("update_missing", "false").lower() == "true" # More complex logic, implement later if needed

    game_urls_to_process = []
    source_description = ""

    if single_game_url_param:
        game_urls_to_process.append(single_game_url_param)
        source_description = f"single URL: {single_game_url_param}"
    elif process_from_firestore_param:
        try:
            query = db.collection('games').where('mentone_playing', '==', True) # Focus on relevant games
            if limit_firestore_games_param > 0:
                query = query.order_by("date", direction=firestore.Query.DESCENDING).limit(limit_firestore_games_param)
            
            for game_doc in query.stream():
                game_d = game_doc.to_dict()
                if game_d.get('url') and game_d['url'].startswith("http"): # Basic URL validation
                    game_urls_to_process.append(game_d['url'])
            source_description = f"Firestore query (limit {limit_firestore_games_param})"
            logger.info(f"Fetched {len(game_urls_to_process)} game URLs from Firestore.")
        except Exception as e_fs_fetch:
            logger.error(f"Error fetching game URLs from Firestore: {e_fs_fetch}", exc_info=True)
            return https_fn.Response(json.dumps({"status":"error", "message":f"Error fetching from Firestore: {e_fs_fetch}"}),
                                   status=500, mimetype="application/json", headers=CORS_HEADERS)
    else:
        return https_fn.Response(json.dumps({"status":"error", "message":"No processing mode specified. Provide 'game_url' or set 'process_from_firestore=true'."}),
                               status=400, mimetype="application/json", headers=CORS_HEADERS)

    if not game_urls_to_process:
        return https_fn.Response(json.dumps({"status":"success", "message":f"No game URLs to process from {source_description}."}),
                               status=200, mimetype="application/json", headers=CORS_HEADERS)

    logger.info(f"Starting venue extraction from {len(game_urls_to_process)} game URLs ({source_description}). Dry run: {dry_run_param}")
    
    venues_extracted_this_run = {} # Store by venue_id to count unique venues
    pages_scraped_count = 0
    venues_saved_count = 0
    errors_scraping = 0
    errors_saving = 0
    start_time_overall = time.time()

    for i, game_url in enumerate(game_urls_to_process):
        logger.debug(f"Processing URL {i+1}/{len(game_urls_to_process)}: {game_url}")
        response = make_request_cf(game_url, session=session)
        pages_scraped_count += 1
        if not response:
            errors_scraping += 1
            continue
        
        soup = BeautifulSoup(response.text, 'html.parser')
        venue_info = extract_venue_info_cf(soup, game_url)

        if venue_info and venue_info.get('id'):
            success, status_msg = save_venue_cf(db, venue_info, dry_run_param)
            if success:
                venues_extracted_this_run[venue_info['id']] = venue_info # Add/update in our run's collection
                if status_msg == "saved": venues_saved_count +=1
                elif status_msg == "dry_run" and dry_run_param : venues_saved_count +=1 # Count dry run "saves"
            else: # status_msg == "error" or "missing_id_or_name"
                errors_saving += 1
        else:
            logger.warning(f"No valid venue data extracted from {game_url}")
            errors_scraping +=1 # Count as scraping error if no usable data

        if i < len(game_urls_to_process) - 1:
             time.sleep(DELAY_BETWEEN_REQUESTS_CF)

    duration_overall = time.time() - start_time_overall
    summary_msg = (
        f"Venue extraction finished in {duration_overall:.2f}s. "
        f"URLs processed: {pages_scraped_count}. Unique venues identified/updated: {len(venues_extracted_this_run)}. "
        f"Venues saved/dry-run: {venues_saved_count}. "
        f"Scraping errors: {errors_scraping}. Saving errors: {errors_saving}."
    )
    logger.info(summary_msg)
    if dry_run_param: logger.info("DRY RUN active. No actual database writes occurred for 'saved' venues.")

    return https_fn.Response(
        json.dumps({
            "status": "success", "message": summary_msg,
            "data": {
                "urls_processed": pages_scraped_count,
                "unique_venues_identified_in_run": len(venues_extracted_this_run),
                "venues_saved_or_dryrun": venues_saved_count,
                "scraping_errors": errors_scraping,
                "saving_errors": errors_saving,
                "duration_seconds": round(duration_overall, 2),
                "dry_run": dry_run_param,
                "source": source_description,
                "extracted_venues_summary": [{v['id']: v['name']} for v_id, v in venues_extracted_this_run.items()] # Summary list
            }
        }),
        status=200, mimetype="application/json", headers=CORS_HEADERS
    )
