# Manages HTTP requests with robust retry mechanisms
# Includes sensible defaults for browser-like requests
# Provides session management to optimize connections
# Contains error handling and logging for network issues
# Includes utility functions like URL building

import requests
import logging
import time
import random
from urllib.parse import urljoin
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Default headers to mimic a browser
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Cache-Control': 'max-age=0',
}

def create_session(retries=3, backoff_factor=0.3, status_forcelist=(500, 502, 504)):
    """Create a requests session with retry functionality.

    Args:
        retries: Number of retries for failed requests
        backoff_factor: Backoff factor for retries
        status_forcelist: HTTP status codes to retry on

    Returns:
        requests.Session: Configured session object
    """
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.headers.update(DEFAULT_HEADERS)
    return session

def make_request(url, method='GET', headers=None, params=None, data=None, json=None,
                 timeout=30, allow_redirects=True, session=None, sleep_range=(1, 3)):
    """Make an HTTP request with retry and error handling.

    Args:
        url: URL to request
        method: HTTP method (GET, POST, etc.)
        headers: Optional headers to add/override defaults
        params: Optional URL parameters
        data: Optional form data
        json: Optional JSON data
        timeout: Request timeout in seconds
        allow_redirects: Whether to follow redirects
        session: Optional requests.Session to use (creates one if None)
        sleep_range: Tuple of (min, max) seconds to sleep before request

    Returns:
        requests.Response or None: Response object or None if failed
    """
    # Sleep randomly to avoid rapid requests
    if sleep_range:
        time.sleep(random.uniform(sleep_range[0], sleep_range[1]))

    # Use provided session or create a new one
    use_session = session if session else create_session()

    # Merge headers with defaults
    request_headers = DEFAULT_HEADERS.copy()
    if headers:
        request_headers.update(headers)

    try:
        logger.debug(f"Making {method} request to {url}")
        response = use_session.request(
            method=method,
            url=url,
            headers=request_headers,
            params=params,
            data=data,
            json=json,
            timeout=timeout,
            allow_redirects=allow_redirects
        )

        # Log response info
        logger.debug(f"Response status: {response.status_code}")

        # Raise for status to trigger retries if needed
        response.raise_for_status()
        return response

    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response content: {e.response.text[:500]}...")
        return e.response if hasattr(e, 'response') else None

    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error when requesting {url}")
        return None

    except requests.exceptions.Timeout:
        logger.error(f"Timeout error when requesting {url}")
        return None

    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {e}")
        return None

    finally:
        # Only close the session if we created it
        if session is None and use_session:
            use_session.close()

def build_url(base_url, path):
    """Properly join base URL and path components.

    Args:
        base_url: Base URL
        path: Path to join to base URL

    Returns:
        str: Full URL
    """
    return urljoin(base_url, path)