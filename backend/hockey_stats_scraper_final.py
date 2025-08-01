#!/usr/bin/env python3
"""
Scrape player game counts from Hockey Victoria team statistics pages.

This script uses Selenium to automate a headless web browser, load a list of
Hockey Victoria team statistics pages and extract the number of games played
(`Attended`) by each player along with the competition grade they played in.

Running the script will produce a CSV file and log messages both to the console
and to a file named ``scraper.log``.  The log file contains detailed diagnostic
information about each page scraped, which can be helpful for troubleshooting.
"""

import csv
import datetime as _dt
import logging
import re
from typing import List, Dict
from collections import defaultdict

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# List of team statistics URLs to scrape.
TEAM_URLS: List[str] = [
    "https://www.hockeyvictoria.org.au/games/team-stats/21935?team_id=337089",
    "https://www.hockeyvictoria.org.au/games/team-stats/21935?team_id=337090",
    "https://www.hockeyvictoria.org.au/games/team-stats/21935?team_id=337086",
    "https://www.hockeyvictoria.org.au/games/team-stats/21935?team_id=337087",
    "https://www.hockeyvictoria.org.au/games/team-stats/21935?team_id=337088",
    "https://www.hockeyvictoria.org.au/games/team-stats/21935?team_id=337085",
]

# Define grade hierarchy from highest to lowest
grade_hierarchy = [
    "Men's Vic League 1",
    "Men's Vic League 1 Reserves",
    "Men's Pennant B",
    "Men's Pennant C",
    "Men's Pennant E South East",
    "Men's Metro 2 South",
]

def _extract_grade(title_text: str) -> str:
    """Return the competition grade from a page heading."""
    if '·' in title_text:
        after_dot = title_text.split('·', 1)[1].strip()
    else:
        after_dot = title_text
    if '-' in after_dot:
        grade = after_dot.split('-', 1)[0].strip()
    else:
        grade = after_dot.strip()
    return grade

def _clean_player_name(raw_name: str) -> str:
    """Sanitise a player's name by stripping row numbers and annotations."""
    cleaned = re.sub(r'^\d+\s*\.?\s*', '', raw_name)
    cleaned = re.sub(r'\(\s*#?\d+\s*\)', '', cleaned)
    cleaned = cleaned.replace('(fill-in)', '')
    cleaned = ' '.join(cleaned.split()).strip(', ')
    return cleaned

def _close_cookie_banner(driver: webdriver.Remote, url: str) -> None:
    """Attempt to close a cookie consent banner if present."""
    try:
        button = driver.find_element(By.ID, "onetrust-accept-btn-handler")
        button.click()
        logging.debug("Clicked cookie banner on %s", url)
        return
    except NoSuchElementException:
        pass
    try:
        button = driver.find_element(By.CSS_SELECTOR, "button[aria-label='Accept Cookies']")
        button.click()
        logging.debug("Clicked alternative cookie banner on %s", url)
    except Exception:
        logging.debug("No cookie banner to close on %s", url)

def scrape_team_page(driver: webdriver.Remote, url: str) -> List[Dict[str, str]]:
    """Load a team statistics page and extract player names and game counts."""
    logging.info("Scraping %s", url)
    driver.get(url)
    _close_cookie_banner(driver, url)

    # Wait up to 30 seconds for either a table row or the DataTables wrapper.
    try:
        WebDriverWait(driver, 30).until(
            EC.any_of(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr")),
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.dataTables_wrapper")),
            )
        )
    except TimeoutException:
        logging.warning("Timeout waiting for table rows on %s", url)
        return []

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(driver.page_source, "html.parser")

    # Extract competition grade from the heading
    grade = ''
    for heading_tag in ["h1", "h2", "h3"]:
        heading_elem = soup.find(heading_tag)
        if heading_elem and 'Senior Competition' in heading_elem.get_text():
            grade = _extract_grade(heading_elem.get_text(strip=True))
            break
    if not grade:
        generic_heading = soup.find(string=lambda s: s and '·' in s)
        if generic_heading:
            grade = _extract_grade(str(generic_heading))
    if grade:
        logging.debug("Extracted grade '%s' from page %s", grade, url)
    else:
        logging.debug("Unable to extract grade from page %s", url)

    table = soup.find('table')
    if not table:
        logging.warning("No table found on %s", url)
        return []
    tbody = table.find('tbody')
    if not tbody:
        logging.warning("No table body found on %s", url)
        return []

    rows = tbody.find_all('tr')
    logging.info(
        "Found %d rows in table for grade '%s' on %s",
        len(rows), grade if grade else '?', url
    )

    results: List[Dict[str, str]] = []
    for row in rows:
        # Include both <th> and <td> cells. Some tables use <th> for the index.
        cells = row.find_all(["th", "td"])
        if not cells:
            logging.debug("Skipping row with no cells on %s", url)
            continue
        texts = [c.get_text(strip=True) for c in cells]
        # Determine which cell contains the player's name.
        name_index = 0
        if texts and re.match(r'^\d+\.?$', texts[0]):
            name_index = 1
        # Find the first purely numeric cell after the name for games attended
        attended_index = None
        for i in range(name_index + 1, len(texts)):
            if re.match(r'^\d+$', texts[i]):
                attended_index = i
                break
        if attended_index is None:
            logging.debug("Skipping row with no numeric attendance value: %s", texts)
            continue
        raw_name = texts[name_index]
        attended_text = texts[attended_index]
        name = _clean_player_name(raw_name)
        try:
            games_attended = int(attended_text)
        except ValueError:
            logging.debug("Skipping row because games_attended is not an integer: %s", texts)
            continue
        results.append({'grade': grade, 'player': name, 'games_attended': games_attended})
        logging.debug("Added record: grade='%s', player='%s', games_attended=%d",
                      grade, name, games_attended)
    return results

def main() -> None:
    """Entry point: scrape all configured team pages and write to CSV."""
    # Configure logging: INFO to console, DEBUG to file
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    logger = logging.getLogger()
    file_handler = logging.FileHandler('scraper.log', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S')
    )
    logger.addHandler(file_handler)

    # Configure headless Chrome with a realistic user agent
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(options=chrome_options)
    all_results: List[Dict[str, str]] = []
    try:
        for url in TEAM_URLS:
            team_results = scrape_team_page(driver, url)
            all_results.extend(team_results)
    finally:
        driver.quit()

    if not all_results:
        logging.warning("No data extracted.")
        return

    # Use date and time in the filename to avoid name clashes if the script runs
    # multiple times in a day (e.g. when the CSV is still open).
    dt_now = _dt.datetime.now()
    timestamp_str = dt_now.strftime("%Y%m%d_%H%M%S")
    output_filename = f"hockey_player_game_counts_{timestamp_str}.csv"
    fieldnames = ['grade', 'player', 'games_attended']
    with open(output_filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_results)
    logging.info("Saved %d records to %s", len(all_results), output_filename)

    # -------------------------------------------------------------
    # Compute ratio of games played in each grade relative to higher grades
    # according to the specified grade hierarchy.  A player is deemed
    # eligible to play finals in a grade if they have played at least 50% of
    # their games in that grade compared to all higher grades combined.

    # Aggregate games attended per player per grade
    player_grade_counts: defaultdict[tuple, int] = defaultdict(int)
    for record in all_results:
        key = (record['player'], record['grade'])
        player_grade_counts[key] += record['games_attended']

    ratio_records = []
    players = {rec['player'] for rec in all_results}
    for player in sorted(players):
        # Total games across all grades for this player
        total_games = sum(player_grade_counts.get((player, g), 0) for g in grade_hierarchy)
        cumulative_higher = 0
        for grade in grade_hierarchy:
            g_count = player_grade_counts.get((player, grade), 0)
            # Skip grades where the player has not played any games.  We still
            # update the cumulative count so lower grades account for higher
            # games, but we don't produce an output record for zero games.
            if g_count == 0:
                cumulative_higher += g_count
                continue
            # Ratio of games played at this grade or lower versus total games.
            # Equivalent to 1 minus the proportion of games in higher grades.
            ratio = ((total_games - cumulative_higher) / total_games) if total_games > 0 else 0.0
            ratio_records.append({
                'grade': grade,
                'player': player,
                'games_attended': g_count,
                'games_in_higher_grades': cumulative_higher,
                'total_games': total_games,
                'ratio': ratio,
                'eligible': ratio >= 0.5,
            })
            # Update cumulative higher games with the current grade count
            cumulative_higher += g_count

    # Write ratio data to its own CSV file.  Each record includes the
    # number of games played at this grade (``games_attended``), the total
    # games played across all grades for the player (``total_games``), the
    # number of games played in higher grades (``games_in_higher_grades``),
    # the computed ratio of games at this grade or lower versus total, and
    # an ``eligible`` flag indicating whether the ratio is at least 50%.
    ratio_output_filename = f"hockey_player_game_ratios_{timestamp_str}.csv"
    ratio_fieldnames = [
        'grade', 'player', 'games_attended',
        'games_in_higher_grades', 'total_games', 'ratio', 'eligible'
    ]
    with open(ratio_output_filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=ratio_fieldnames)
        writer.writeheader()
        for rec in ratio_records:
            # Format the ratio to three decimal places for readability
            rec_copy = rec.copy()
            rec_copy['ratio'] = f"{rec_copy['ratio']:.3f}"
            writer.writerow(rec_copy)
    logging.info("Saved %d ratio records to %s", len(ratio_records), ratio_output_filename)



if __name__ == '__main__':
    main()
