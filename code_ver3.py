import aiohttp
import asyncio
import aiosqlite
from bs4 import BeautifulSoup

# Константы
SEARCH_QUERIES = ["strategy", "rpg"]  # Список запросов
MAX_PAGES = 5  # Максимальное количество страниц для парсинга
BASE_URL = "https://store.steampowered.com/search/"
DELAY = 2  # Задержка между запросами в секундах
DOB_PAYLOAD = {"ageDay": "08", "ageMonth": "May", "ageYear": "2005"}  # Дата рождения

# SQLite schema
CREATE_TABLE_QUERY = """
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    price TEXT,
    rating TEXT,
    developer TEXT,
    genres TEXT,
    release_date TEXT
);
"""

INSERT_QUERY = """
INSERT INTO games (title, price, rating, developer, genres, release_date)
VALUES (?, ?, ?, ?, ?, ?);
"""

def construct_url(query, page):
    params = {
        "term": query,
        "page": page,
        "filter": "popularnew",
        "cc": "us"  # Добавляем параметр для полной загрузки контента
    }
    query_string = "&".join(f"{key}={value}" for key, value in params.items())
    return f"{BASE_URL}?{query_string}"

async def fetch_page(session, url, post_data=None):
    if post_data:
        async with session.post(url, data=post_data) as response:
            if response.status == 200:
                return await response.text()
            else:
                print(f"Failed to fetch {url}: {response.status}")
                return None
    else:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.text()
            else:
                print(f"Failed to fetch {url}: {response.status}")
                return None

async def parse_game_details(session, game_url):
    html = await fetch_page(session, game_url)

    # Проверяем, требуется ли подтверждение возраста
    if html and "agecheck" in html:
        print(f"Age check required for {game_url}, submitting DOB.")
        html = await fetch_page(session, game_url, post_data=DOB_PAYLOAD)

    if not html:
        return "Unknown", "Unknown", "Unknown"

    soup = BeautifulSoup(html, "lxml")
    developer = soup.select_one("div.dev_row a")
    developer = developer.get_text(strip=True) if developer else "Unknown"

    genres = soup.select(".details_block a[href*='genre']")
    genres = ";".join([genre.get_text(strip=True) for genre in genres]) if genres else "Unknown"

    release_date = soup.select_one("div.date")
    release_date = release_date.get_text(strip=True) if release_date else "Unknown"

    return developer, genres, release_date

async def parse_page(session, html):
    soup = BeautifulSoup(html, "lxml")
    results = []
    for game in soup.select(".search_result_row"):
        title = game.select_one(".title").get_text(strip=True)
        price = game.select_one(".search_price").get_text(strip=True) if game.select_one(".search_price") else "Free"
        rating = game.select_one(".search_review_summary")
        rating_text = rating["data-tooltip-html"] if rating else "No reviews"
        game_url = game["href"]

        developer, genres, release_date = await parse_game_details(session, game_url)

        results.append((title, price, rating_text, developer, genres, release_date))
    return results

async def save_to_db(db_path, games):
    async with aiosqlite.connect(db_path) as db:
        await db.execute(CREATE_TABLE_QUERY)
        await db.executemany(INSERT_QUERY, games)
        await db.commit()

async def scrape_query(query, max_pages):
    games = []
    async with aiohttp.ClientSession() as session:
        for page in range(1, max_pages + 1):
            url = construct_url(query, page)
            print(f"Fetching: {url}")
            html = await fetch_page(session, url)
            if html:
                page_results = await parse_page(session, html)
                if not page_results:  # Если на странице нет результатов, выходим
                    break
                games.extend(page_results)
            await asyncio.sleep(DELAY)
    return games

async def main():
    db_path = "results.db"
    all_games = []
    for query in SEARCH_QUERIES:
        print(f"Scraping query: {query}")
        games = await scrape_query(query, MAX_PAGES)
        all_games.extend(games)

    await save_to_db(db_path, all_games)
    print(f"Saved {len(all_games)} games to the database.")

if __name__ == "__main__":
    asyncio.run(main())
