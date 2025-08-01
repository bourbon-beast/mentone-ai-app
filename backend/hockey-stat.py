import csv
import logging
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Ordered from highest to lowest grade
GRADE_ORDER = [
    "Men's Vic League 1",
    "Men's Vic League 1 Reserves",
    "Men's Pennant B",
    "Men's Pennant C",
    "Men's Pennant E South East",
    "Men's Metro 2 South"
]

TEAM_URLS = {
    "Men's Vic League 1": "https://www.hockeyvictoria.org.au/games/team-stats/21935?team_id=337089",
    "Men's Vic League 1 Reserves": "https://www.hockeyvictoria.org.au/games/team-stats/21935?team_id=337090",
    "Men's Pennant B": "https://www.hockeyvictoria.org.au/games/team-stats/21935?team_id=337086",
    "Men's Pennant C": "https://www.hockeyvictoria.org.au/games/team-stats/21935?team_id=337087",
    "Men's Pennant E South East": "https://www.hockeyvictoria.org.au/games/team-stats/21935?team_id=337088",
    "Men's Metro 2 South": "https://www.hockeyvictoria.org.au/games/team-stats/21935?team_id=337085",
}


def get_page_content(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        logging.info(f"Scraping {url}")
        page.goto(url, timeout=60000)
        page.wait_for_selector(".MuiTable-root")
        html = page.content()
        browser.close()
        return html


def extract_game_data(html: str, grade: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        logging.warning("No table found in HTML")
        return []

    rows = table.find_all("tr")
    logging.info(f"Found {len(rows)} rows")
    results = []
    for row in rows[1:]:
        cols = row.find_all("td")
        if len(cols) < 5:
            continue
        player = cols[0].text.strip()
        games_attended = int(cols[4].text.strip())
        results.append({"grade": grade, "player": player, "games_attended": games_attended})
    return results


def calculate_ratios(all_results: list, weeks_remaining: int) -> list:
    player_grade_counts = defaultdict(int)
    player_total_counts = defaultdict(int)
    player_grade_map = defaultdict(dict)

    for result in all_results:
        key = (result["player"], result["grade"])
        player_grade_counts[key] += result["games_attended"]
        player_total_counts[result["player"]] += result["games_attended"]
        player_grade_map[result["player"]][result["grade"]] = result["games_attended"]

    final_results = []
    for player, grade_counts in player_grade_map.items():
        for grade in grade_counts:
            games_in_grade = grade_counts[grade]
            lower_or_same_grades = GRADE_ORDER[GRADE_ORDER.index(grade):]
            games_in_lower_or_same = sum(
                player_grade_map[player].get(g, 0) for g in lower_or_same_grades
            )
            total = sum(player_grade_map[player].values())
            ratio = games_in_lower_or_same / total if total > 0 else 0
            eligible = ratio >= 0.5

            # Color coding logic
            required = int(total / 2 + 0.5)
            needed = max(0, required - games_in_lower_or_same)
            if eligible:
                status = "green"
            elif needed <= weeks_remaining:
                status = "orange"
            else:
                status = "red"

            final_results.append({
                "grade": grade,
                "player": player,
                "games_attended": games_in_grade,
                "games_in_lower_or_same_grades": games_in_lower_or_same,
                "total_games": total,
                "ratio": round(ratio, 3),
                "eligible": eligible,
                "status": status,
            })
    return final_results


def write_csv(data: list):
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = Path(f"hockey_player_game_ratios_{now}.csv")
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "grade", "player", "games_attended", "games_in_lower_or_same_grades",
            "total_games", "ratio", "eligible", "status"
        ])
        writer.writeheader()
        for row in data:
            writer.writerow(row)
    logging.info(f"CSV saved to {output_file}")


def main():
    if len(sys.argv) != 2:
        print("Usage: python hockey_stats_scraper.py <weeks_remaining>")
        return

    weeks_remaining = int(sys.argv[1])
    all_results = []
    for grade, url in TEAM_URLS.items():
        html = get_page_content(url)
        grade_data = extract_game_data(html, grade)
        all_results.extend(grade_data)

    if not all_results:
        logging.warning("No data extracted.")
        return

    processed = calculate_ratios(all_results, weeks_remaining)
    write_csv(processed)


if __name__ == "__main__":
    main()

