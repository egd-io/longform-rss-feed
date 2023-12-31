import datetime
import feedparser
import logging
import requests
import yaml

from bs4 import BeautifulSoup
from dateutil import parser
from vendor.svpino.rfeed import rfeed
from urllib.parse import urlparse

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

with open("config.yml", "r") as config:
    try:
        config = yaml.safe_load(config)
    except yaml.YAMLError as exc:
        logging.error(exc)


def get_feed(url):
    feed = feedparser.parse(url)
    if "title" not in feed["feed"]:
        raise ValueError(f"Feed not valid: {url}")

    return feed


def get_entries(feed, date_term):
    now = datetime.datetime.now(datetime.timezone.utc)
    days_ago = datetime.timedelta(days=config["days_old"])
    since = now - days_ago

    entries = []

    for entry in feed["entries"]:
        published = parser.parse(entry[date_term])

        if published > since:
            entries.append(entry)

    return entries


def parse_entries(pub_name, entries, date_term, search_value):
    items = []

    for entry in entries:
        soup = BeautifulSoup(entry["content"][0]["value"], "html.parser")

        if pub_name == "Longreads":
            item = _parse_longreads_entry(
                soup, entry, date_term, search_value, pub_name
            )
            if item is not None:
                items.append(item)
        elif pub_name == "The Browser":
            items += _parse_the_browser_entry(soup, entry, date_term, pub_name)
        elif pub_name == "The Sunday Long Read":
            items += _parse_the_sunday_long_read(soup, entry, date_term, pub_name)

    return items


def save_feed(items, filename):
    feed = rfeed.Feed(
        title=config["output"]["title"],
        link=config["output"]["link"],
        description=config["output"]["description"],
        language=config["output"]["language"],
        lastBuildDate=datetime.datetime.now(datetime.timezone.utc),
        items=items,
    )

    _write_feed(feed.rss(), filename)


def save_item(title, link, description, pub_date):
    return rfeed.Item(
        title=title,
        link=_get_final_url(link.split("?")[0]),
        description=description,
        pubDate=pub_date,
    )


def _get_final_url(url):
    logging.info(f"Checking URL for redirects: {url}")
    response = requests.get(url, allow_redirects=True)

    if len(response.history) > 0:
        logging.info(f"Found final URL: {response.url.split('?')[0]}")

    return response.url.split("?")[0]


def _parse_longreads_entry(soup, entry, date_term, search_value, pub_name):
    url = soup.find("a", string=search_value)

    if url is None:
        logging.info(f"URL for {entry['title']} is not valid. Skipping...")
        return None
    else:
        return save_item(
            entry["title"], url["href"], pub_name, parser.parse(entry[date_term])
        )


def _parse_the_browser_entry(soup, entry, date_term, pub_name):
    items = []
    headers = soup.find_all("h3")

    for header in headers:
        if isinstance(header.contents[0], str):
            logging.info(
                f"URL for {header.contents[0].string} is not valid. Skipping..."
            )
        else:
            items.append(
                save_item(
                    header.contents[0].string,
                    header.contents[0]["href"],
                    pub_name,
                    parser.parse(entry[date_term]),
                )
            )

    return items


def _parse_the_sunday_long_read(soup, entry, date_term, pub_name):
    items = []
    headers = soup.find_all("h1")

    for header in headers:
        if len(header.contents) < 2:
            logging.info(
                f"URL for {header.contents[0].string} is not valid. Skipping..."
            )
        elif isinstance(header.contents[1], str):
            logging.info(
                f"URL for {header.contents[1].string} is not valid. Skipping..."
            )
        else:
            items.append(
                save_item(
                    header.contents[1].string,
                    header.contents[1]["href"],
                    pub_name,
                    parser.parse(entry[date_term]),
                )
            )

    return items


def _write_feed(feed, filename):
    with open(filename, "w") as output:
        output.write(feed)


if __name__ == "__main__":
    final_entries = []
    for publication in config["publications"]:
        logging.info(f"Getting {publication['name']} feed...")

        try:
            feed = get_feed(publication["url"])
        except ValueError as err:
            logging.error(err)

        logging.info(f"Filtering out articles older than {config['days_old']} days...")
        entries = get_entries(feed, publication["date_term"])
        logging.info(f"Found {len(entries)} items from {publication['name']}")

        if "search" in publication:
            final_entries += parse_entries(
                publication["name"],
                entries,
                publication["date_term"],
                publication["search"]["value"],
            )
        else:
            for entry in entries:
                final_entries.append(
                    save_item(
                        entry["title"],
                        entry["link"],
                        publication["name"],
                        parser.parse(entry[publication["date_term"]]),
                    )
                )

    logging.info(
        f"Writing {len(final_entries)} total items to {config['output']['filename']}..."
    )
    save_feed(final_entries, config["output"]["filename"])
