import hashlib
import json
import logging
import os
import re
import math
import time
from pathlib import Path
from urllib.request import Request, urlopen
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit

import feedparser
from confluent_kafka import Producer
from dotenv import load_dotenv


load_dotenv(Path(__file__).with_name(".env"), override=False)


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("NewsProducer")


RSS_FEEDS = {
    "Companies":[
        "https://www.livemint.com/rss/companies",
        "https://in.investing.com/rss/news_356.rss"
        ],
    "economy": [
        "https://www.cnbctv18.com/common-feed/v1/c18/economy.xml",
        "https://economictimes.indiatimes.com/news/economy/rssfeeds/13765978.cms",
        "https://in.investing.com/rss/news_14.rss"
    ],
    "markets": [
        "https://www.cnbctv18.com/common-feed/v1/c18/market.xml",
        "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "https://www.livemint.com/rss/markets",
        "https://in.investing.com/rss/market_overview.rss",
        "https://in.investing.com/rss/stock.rss"
    ],
    "business": [
        "https://www.cnbctv18.com/common-feed/v1/c18/business.xml",
        "https://feeds.feedburner.com/ndtvprofit-latest"
    ],
    "technology": [
        "https://economictimes.indiatimes.com/tech/rssfeeds/13357270.cms",
        "https://www.livemint.com/rss/technology","https://feeds.feedburner.com/gadgets360-latest"
    ],
    "finance": [
        "https://www.cnbctv18.com/common-feed/v1/c18/finance.xml",
        "https://www.livemint.com/rss/budget"
    ],
    "Money": [
        "https://www.livemint.com/rss/money",
    ],
    "Announcements":["https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml"],
    "Annual Reports":["https://nsearchives.nseindia.com/content/RSS/Annual_Reports.xml"],
    "Board Meetings":["https://nsearchives.nseindia.com/content/RSS/Board_Meetings.xml"],
    "Corporate Actions":["https://nsearchives.nseindia.com/content/RSS/Corporate_action.xml"],
    "Corporate Governance":["https://nsearchives.nseindia.com/content/RSS/Corporate_Governance.xml"],
    "Financial Results":["https://nsearchives.nseindia.com/content/RSS/Financial_Results.xml"],
    "Insider Trading":["https://nsearchives.nseindia.com/content/RSS/InsiderTrading.xml"]
}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.parts.append(text)


def strip_html(value):
    parser = _TextExtractor()
    parser.feed(value or "")
    return " ".join(parser.parts)


def canonical_url(value):
    parts = urlsplit((value or "").strip())
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path,
            parts.query,
            "",
        )
    )


def news_id(url):
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def utc_now_text():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def rss_date_text(entry):
    parsed = getattr(entry, "published_parsed", None) or getattr(
        entry, "updated_parsed", None
    )
    if not parsed:
        return None
    return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def normalize_category(category):
    value = re.sub(r"[^a-z0-9_-]+", "_", str(category).strip().lower()).strip("_")
    if not value:
        raise ValueError("News category is missing or invalid")
    return value


def topic_for_category(category):
    prefix = os.getenv("NEWS_RAW_TOPIC_PREFIX", "news_")
    return f"{prefix}{normalize_category(category)}"


def delivery_report(error, message):
    if error is not None:
        logger.error("Kafka delivery failed topic=%s error=%s", message.topic(), error)
        return

    key = message.key().decode("utf-8", errors="replace") if message.key() else ""
    logger.info(
        "Published raw news topic=%s partition=%s key=%s",
        message.topic(),
        message.partition(),
        key,
    )


class NewsKafkaProducer:
    def __init__(self, bootstrap_servers=None):
        servers = bootstrap_servers or os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:29092"
        )
        self.feed_timeout = float(os.getenv("NEWS_RSS_TIMEOUT_SECONDS", "30"))
        if not math.isfinite(self.feed_timeout) or self.feed_timeout <= 0:
            raise ValueError("NEWS_RSS_TIMEOUT_SECONDS must be a finite positive number")
        self.producer = Producer(
            {
                "bootstrap.servers": servers,
                "client.id": os.getenv("KAFKA_CLIENT_ID", "rss-news-producer"),
                "acks": "all",
                "enable.idempotence": True,
            }
        )

    @staticmethod
    def build_event(category, feed, entry):
        link = canonical_url(getattr(entry, "link", ""))
        if not link:
            raise ValueError("Article is missing a URL")

        return {
            "event_type": "news.raw",
            "schema_version": 1,
            "news_id": news_id(link),
            "category": normalize_category(category),
            "source": feed.feed.get("title", "unknown"),
            "title": strip_html(getattr(entry, "title", "")),
            "summary": strip_html(getattr(entry, "summary", "")),
            "link": link,
            "published_at": rss_date_text(entry),
            "fetched_at": utc_now_text(),
        }

    def fetch_feed(self, url):
        """Fetch with a socket timeout; parse bytes without another network call."""
        started = time.monotonic()
        request = Request(
            url,
            headers={
                "User-Agent": "StockAnalysis-NewsRSS/1.0",
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
            },
        )
        with urlopen(request, timeout=self.feed_timeout) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            content = response.read()
        feed = feedparser.parse(content)
        if not feed.get("version"):
            raise ValueError(
                f"Response is not an RSS/Atom feed (status={status}, content_type={content_type})"
            )
        logger.info(
            "RSS fetch completed feed=%s status=%s elapsed_seconds=%.2f bytes=%s entries=%s",
            url, status, time.monotonic() - started, len(content), len(feed.entries),
        )
        if not feed.entries:
            logger.info("RSS feed contains no entries feed=%s", url)
        return feed

    def fetch_and_publish(self):
        produced = 0

        for category, urls in RSS_FEEDS.items():
            topic = topic_for_category(category)

            for url in urls:
                try:
                    logger.info("Parsing feed=%s category=%s", url, category)
                    feed = self.fetch_feed(url)

                    if feed.get("bozo", 0) == 1:
                        logger.warning(
                            "Feed reported malformed content; processing available entries url=%s",
                            url,
                        )

                    for entry in feed.entries:
                        try:
                            event = self.build_event(category, feed, entry)
                            while True:
                                try:
                                    self.producer.poll(0)
                                    self.producer.produce(
                                        topic=topic,
                                        key=event["news_id"].encode("utf-8"),
                                        value=json.dumps(
                                            event,
                                            ensure_ascii=False,
                                            separators=(",", ":"),
                                        ).encode("utf-8"),
                                        on_delivery=delivery_report,
                                    )
                                    break
                                except BufferError:
                                    logger.warning(
                                        "Kafka buffer full; waiting before retrying article"
                                    )
                                    self.producer.poll(1)
                            produced += 1
                        except Exception as error:
                            logger.exception(
                                "Article processing failed feed=%s error_type=%s",
                                url,
                                type(error).__name__,
                            )
                except Exception as error:
                    logger.exception(
                        "RSS feed failed url=%s error_type=%s",
                        url,
                        type(error).__name__,
                    )

        logger.info("Flushing raw news messages count=%s", produced)
        undelivered = self.producer.flush(30)
        if undelivered:
            raise RuntimeError(f"Kafka flush timed out with {undelivered} messages")

        logger.info("RSS ingestion completed count=%s", produced)


if __name__ == "__main__":
    NewsKafkaProducer().fetch_and_publish()
