# debug_fetch_grade_page.py
import requests
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
GRADE_URL = "https://www.hockeyvictoria.org.au/games/22076/37393/" # The specific grade page
REQUEST_TIMEOUT = 15
SCRIPT_VERSION = "debug-1.0"
# --- End Configuration ---

def make_request(url):
    try:
        logger.info(f"Requesting URL: {url}")
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                'User-Agent': f'MentoneHockeyApp-Debug/{SCRIPT_VERSION}',
                'Accept': 'text/html,application/xhtml+xml',
            }
        )
        response.raise_for_status() # Check for HTTP errors (like 404, 500)
        logger.info(f"Request successful (Status Code: {response.status_code})")
        return response.text # Return the HTML content
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for {url}: {e}")
        return None

if __name__ == "__main__":
    html_content = make_request(GRADE_URL)
    if html_content:
        print("\n--- HTML Content Start ---\n")
        print(html_content)
        print("\n--- HTML Content End ---\n")
        logger.info("Successfully fetched and printed HTML content.")
        # Optional: Save to file
        # with open("grade_page_content.html", "w", encoding="utf-8") as f:
        #     f.write(html_content)
        # logger.info("Saved HTML content to grade_page_content.html")
    else:
        logger.error("Could not retrieve HTML content.")