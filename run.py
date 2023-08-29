import datetime
import feedparser
import logging
import requests
import yaml

from bs4 import BeautifulSoup
from dateutil import parser
from vendor.svpino.rfeed import rfeed

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
            item = _parse_longreads_entry(soup, entry, date_term, search_value, pub_name)
            if item is not None:
                items.append(item)
        elif pub_name == "The Browser":
            items += _parse_the_browser_entry(soup, entry, date_term, pub_name)
        elif pub_name == "The Sunday Long Read":
            items += _parse_the_sunday_long_read(soup, entry, date_term, pub_name)

    logging.info(f"Found {len(items)} items from {pub_name}")

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


def _get_final_url(url):
    logging.info(f"Checking URL for redirects: {url}")
    response = requests.get(url)

    if len(response.history) > 0:
        logging.info(f"Found final URL: {response.url.split('?')[0]}")

    return response.url.split("?")[0]


def _parse_longreads_entry(soup, entry, date_term, search_value, pub_name):
    url = soup.find("a", string=search_value)

    return _save_item(
        entry["title"], url, pub_name, parser.parse(entry[date_term])
    )


def _parse_the_browser_entry(soup, entry, date_term, pub_name):
    items = []
    headers = soup.find_all("h3")

    for header in headers:
        items.append(
            _save_item(
                header.contents[0].string,
                header.contents[0],
                pub_name,
                parser.parse(entry[date_term]),
            )
        )

    return items


def _parse_the_sunday_long_read(soup, entry, date_term, pub_name):
    items = []
    headers = soup.find_all("h1")

    for header in headers:
        items.append(
            _save_item(
                header.contents[0].string,
                header.contents[0],
                pub_name,
                parser.parse(entry[date_term]),
            )
        )

    return items


def _save_item(title, link, description, pub_date):
    if link is not None:
        return rfeed.Item(
            title=title,
            link=_get_final_url(link["href"].split("?")[0]),
            description=description,
            pubDate=pub_date,
        )


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

        final_entries += parse_entries(
            publication["name"],
            entries,
            publication["date_term"],
            publication["search"]["value"],
        )

    logging.info(f"Writing {len(final_entries)} total items to {config['output']['filename']}...")
    save_feed(final_entries, config["output"]["filename"])
