#!/usr/bin/env python3
"""
Scrape player game counts from Hockey Victoria team statistics pages.

This script uses Selenium to automate a headless web browser, load a list of
Hockey Victoria team statistics pages and extract the number of games played
(`Attended`) by each player along with the competition grade they played in.

Running the script will produce two CSV files:
- One for raw game counts per player and grade
- One for finals eligibility status based on current ratios and remaining games
"""

import csv
import datetime as _dt
import logging
import re
import argparse
from typing import List, Dict
from collections import defaultdict
from math import ceil

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
    cleaned = re.sub(r'^\d+\s*\.?\s*', '', raw_name)
    cleaned = re.sub(r'\(\s*#?\d+\s*\)', '', cleaned)
    cleaned = cleaned.replace('(fill-in)', '')
    cleaned = ' '.join(cleaned.split()).strip(', ')
    return cleaned

def _close_cookie_banner(driver: webdriver.Remote, url: str) -> None:
    try:
        button = driver.find_element(By.ID, "onetrust-accept-btn-handler")
        button.click()
        return
    except NoSuchElementException:
        pass
    try:
        button = driver.find_element(By.CSS_SELECTOR, "button[aria-label='Accept Cookies']")
        button.click()
    except Exception:
        pass

def scrape_team_page(driver: webdriver.Remote, url: str) -> List[Dict[str, str]]:
    driver.get(url)
    _close_cookie_banner(driver, url)

    try:
        WebDriverWait(driver, 30).until(
            EC.any_of(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr")),
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.dataTables_wrapper")),
            )
        )
    except TimeoutException:
        return []

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(driver.page_source, "html.parser")

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

    table = soup.find('table')
    if not table:
        return []
    tbody = table.find('tbody')
    if not tbody:
        return []

    rows = tbody.find_all('tr')
    results: List[Dict[str, str]] = []
    for row in rows:
        cells = row.find_all(["th", "td"])
        if not cells:
            continue
        texts = [c.get_text(strip=True) for c in cells]
        name_index = 0
        if texts and re.match(r'^\d+\.?$', texts[0]):
            name_index = 1
        attended_index = None
        for i in range(name_index + 1, len(texts)):
            if re.match(r'^\d+$', texts[i]):
                attended_index = i
                break
        if attended_index is None:
            continue
        raw_name = texts[name_index]
        attended_text = texts[attended_index]
        name = _clean_player_name(raw_name)
        try:
            games_attended = int(attended_text)
        except ValueError:
            continue
        results.append({'grade': grade, 'player': name, 'games_attended': games_attended})
    return results

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--weeks-remaining', type=int, default=0, help='Weeks remaining in the season')
    args = parser.parse_args()
    weeks_remaining = args.weeks_remaining

    logging.basicConfig(level=logging.INFO)

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--user-agent=Mozilla/5.0")

    driver = webdriver.Chrome(options=chrome_options)
    all_results: List[Dict[str, str]] = []
    try:
        for url in TEAM_URLS:
            team_results = scrape_team_page(driver, url)
            all_results.extend(team_results)
    finally:
        driver.quit()

    if not all_results:
        return

    dt_now = _dt.datetime.now()
    timestamp_str = dt_now.strftime("%Y%m%d_%H%M%S")
    output_filename = f"hockey_player_game_counts_{timestamp_str}.csv"
    fieldnames = ['grade', 'player', 'games_attended']
    with open(output_filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_results)

    player_grade_counts: defaultdict[tuple, int] = defaultdict(int)
    for record in all_results:
        key = (record['player'], record['grade'])
        player_grade_counts[key] += record['games_attended']

    ratio_records = []
    players = {rec['player'] for rec in all_results}
    for player in sorted(players):
        total_games = sum(player_grade_counts.get((player, g), 0) for g in grade_hierarchy)
        cumulative_higher = 0
        for grade in grade_hierarchy:
            g_count = player_grade_counts.get((player, grade), 0)
            if g_count == 0:
                cumulative_higher += g_count
                continue
            percent_in_grade = ((total_games - cumulative_higher) / total_games * 100) if total_games > 0 else 0.0
            games_needed = max(0, ceil(2 * cumulative_higher - total_games))
            if games_needed == 0:
                status = 'green'
            elif games_needed <= weeks_remaining:
                status = 'orange'
            else:
                status = 'red'
            ratio_records.append({
                'Grade': grade,
                'Player': player,
                'Games in grade or below': g_count,
                'Games higher grades': cumulative_higher,
                'Total games': total_games,
                '% Grade or below': round(percent_in_grade, 1),
                'Can qualify': status,
                'To qualify': games_needed,
            })
            cumulative_higher += g_count

    ratio_output_filename = f"hockey_player_finals_eligibility_{timestamp_str}.csv"
    ratio_fieldnames = [
        'Grade', 'Player', 'Games in grade or below',
        'Games higher grades', 'Total games',
        '% Grade or below', 'Can qualify', 'To qualify'
    ]
    with open(ratio_output_filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=ratio_fieldnames)
        writer.writeheader()
        writer.writerows(ratio_records)

if __name__ == '__main__':
    main()
