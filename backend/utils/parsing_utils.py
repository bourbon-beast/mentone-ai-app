# Contains common HTML/data parsing functions
# Handles date parsing with timezone awareness
# Provides functions for extracting IDs from Hockey Victoria URLs
# Includes utilities for working with HTML tables
# Has helper functions for identifying Mentone teams
# Includes debug capabilities like saving HTML for inspection

import logging
import re
from bs4 import BeautifulSoup
from datetime import datetime
import pytz
import json

logger = logging.getLogger(__name__)

# Constants
AUSTRALIA_TZ = pytz.timezone('Australia/Melbourne')

def clean_text(text):
    """Clean text by removing extra whitespace and normalizing.

    Args:
        text: Input text string

    Returns:
        str: Cleaned text
    """
    if not text:
        return ""

    # Replace non-breaking spaces and other whitespace characters
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_number(text, default=None):
    """Extract a number from text.

    Args:
        text: Text containing a number
        default: Default value if no number found

    Returns:
        int, float, or default: Extracted number or default
    """
    if not text:
        return default

    # Extract number using regex
    match = re.search(r'(-?\d+\.?\d*)', text)
    if not match:
        return default

    # Convert to int or float
    value = match.group(1)
    try:
        if '.' in value:
            return float(value)
        return int(value)
    except ValueError:
        return default

def parse_date(date_str, formats=None, default=None, timezone=AUSTRALIA_TZ):
    """Parse date string using multiple possible formats.

    Args:
        date_str: Date string to parse
        formats: List of format strings to try
        default: Default value if parsing fails
        timezone: Timezone to localize the date

    Returns:
        datetime or default: Parsed datetime object or default
    """
    if not date_str:
        return default

    # Default formats to try
    if formats is None:
        formats = [
            '%d/%m/%Y',           # 25/12/2023
            '%d-%m-%Y',           # 25-12-2023
            '%Y-%m-%d',           # 2023-12-25
            '%d %b %Y',           # 25 Dec 2023
            '%d %B %Y',           # 25 December 2023
            '%a %d %b %Y',        # Mon 25 Dec 2023
            '%A %d %B %Y',        # Monday 25 December 2023
            '%d/%m/%Y %H:%M',     # 25/12/2023 14:30
            '%d-%m-%Y %H:%M',     # 25-12-2023 14:30
            '%Y-%m-%d %H:%M',     # 2023-12-25 14:30
            '%d %b %Y %H:%M',     # 25 Dec 2023 14:30
            '%d/%m/%Y %I:%M %p',  # 25/12/2023 2:30 PM
            '%d-%m-%Y %I:%M %p',  # 25-12-2023 2:30 PM
        ]

    # Clean date string
    date_str = clean_text(date_str)

    # Try each format
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            if timezone:
                # Make timezone-aware
                dt = timezone.localize(dt)
            return dt
        except ValueError:
            continue

    logger.warning(f"Failed to parse date: '{date_str}'")
    return default

def extract_competition_id(url):
    """Extract competition ID from Hockey Victoria URL.

    Args:
        url: URL string

    Returns:
        str or None: Extracted ID or None
    """
    # Extract comp_id from various URL patterns
    patterns = [
        r'/games/(\d+)',              # /games/12345
        r'/pointscore/(\d+)/\d+',     # /pointscore/12345/67890
        r'/fixtures\?compID=(\d+)',   # /fixtures?compID=12345
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None

def extract_fixture_id(url):
    """Extract fixture ID from Hockey Victoria URL.

    Args:
        url: URL string

    Returns:
        str or None: Extracted ID or None
    """
    # Extract fixture_id from various URL patterns
    match = re.search(r'/pointscore/\d+/(\d+)', url)
    if match:
        return match.group(1)

    match = re.search(r'/games/\d+/(\d+)', url)
    if match:
        return match.group(1)

    return None

def is_mentone_team(team_name):
    """Check if a team name belongs to Mentone.

    Args:
        team_name: Team name string

    Returns:
        bool: True if Mentone team
    """
    if not team_name:
        return False

    # Case insensitive check for Mentone
    return bool(re.search(r'mentone', team_name, re.IGNORECASE))

def extract_table_data(table, has_header=True):
    """Extract data from HTML table into a list of dictionaries.

    Args:
        table: BeautifulSoup table element
        has_header: Whether the table has header row

    Returns:
        list: List of dictionaries with row data
    """
    if not table:
        return []

    # Get all rows
    rows = table.find_all('tr')
    if not rows:
        return []

    # Extract headers if table has them
    headers = []
    if has_header:
        header_row = rows[0]
        headers = [clean_text(cell.get_text()) for cell in header_row.find_all(['th', 'td'])]
        rows = rows[1:]  # Skip header row

    # Process data rows
    data = []
    for row in rows:
        cells = row.find_all(['td', 'th'])
        if not cells:
            continue

        # Extract cell values
        row_data = [clean_text(cell.get_text()) for cell in cells]

        # Create dictionary if headers exist, otherwise use list
        if headers:
            # Ensure equal lengths by truncating or extending
            if len(row_data) < len(headers):
                row_data.extend([''] * (len(headers) - len(row_data)))
            elif len(row_data) > len(headers):
                row_data = row_data[:len(headers)]

            row_dict = dict(zip(headers, row_data))
            data.append(row_dict)
        else:
            data.append(row_data)

    return data

def save_debug_html(html_content, filename):
    """Save HTML content to file for debugging.

    Args:
        html_content: HTML content string
        filename: Filename to save as
    """
    try:
        with open(f"debug_{filename}.html", 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.debug(f"Saved debug HTML to debug_{filename}.html")
    except Exception as e:
        logger.error(f"Failed to save debug HTML: {e}")

def extract_json_from_script(html, script_contains=None):
    """Extract JSON data from script tags in HTML.

    Args:
        html: HTML content
        script_contains: String that must be in the script tag

    Returns:
        dict or None: Parsed JSON data or None
    """
    soup = BeautifulSoup(html, 'html.parser')
    scripts = soup.find_all('script')

    for script in scripts:
        script_text = script.string
        if not script_text:
            continue

        if script_contains and script_contains not in script_text:
            continue

        # Look for JSON object patterns
        try:
            # Find json pattern like var data = {...}; or window.data = {...};
            json_match = re.search(r'(?:var|window)\.?\w+\s*=\s*({.+?});', script_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                return json.loads(json_str)

            # Look for standalone JSON object
            if script_text.strip().startswith('{') and script_text.strip().endswith('}'):
                return json.loads(script_text)
        except json.JSONDecodeError:
            continue

    return None