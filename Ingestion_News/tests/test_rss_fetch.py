import io
import os
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from news_producer import NewsKafkaProducer

EMPTY = b'<rss version="2.0"><channel><title>NSE</title><link>https://nseindia.com</link><description>News</description></channel></rss>'
ARTICLE = EMPTY.replace(b'</channel>', b'<item><title>Results</title><link>https://example.com/results</link><description>Revenue rose</description></item></channel>')


class RSSFetchTests(unittest.TestCase):
    def producer(self):
        producer = NewsKafkaProducer.__new__(NewsKafkaProducer)
        producer.feed_timeout = 2.5
        producer.producer = Mock()
        producer.producer.flush.return_value = 0
        return producer

    def response(self, content):
        response = Mock()
        response.status = 200
        response.headers = {"Content-Type": "application/xml"}
        response.read.return_value = content
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    @patch("news_producer.urlopen")
    def test_downloads_bytes_with_timeout_and_parses_entries(self, open_url):
        open_url.return_value = self.response(ARTICLE)
        feed = self.producer().fetch_feed("https://example.com/rss")
        self.assertEqual(len(feed.entries), 1)
        self.assertEqual(open_url.call_args.kwargs["timeout"], 2.5)

    @patch("news_producer.urlopen")
    def test_empty_rss_is_valid_and_logged(self, open_url):
        open_url.return_value = self.response(EMPTY)
        with self.assertLogs("NewsProducer", level="INFO") as logs:
            feed = self.producer().fetch_feed("https://example.com/rss")
        self.assertEqual(len(feed.entries), 0)
        self.assertTrue(any("entries=0" in line for line in logs.output))

    @patch("news_producer.urlopen")
    def test_html_response_is_rejected(self, open_url):
        open_url.return_value = self.response(b"<html><body>Access denied</body></html>")
        with self.assertRaisesRegex(ValueError, "not an RSS/Atom"):
            self.producer().fetch_feed("https://example.com/rss")

    @patch("news_producer.RSS_FEEDS", {"Announcements": ["https://example.com/bad", "https://example.com/good"]})
    @patch("news_producer.urlopen")
    def test_timeout_and_http_error_continue_to_next_feed(self, open_url):
        for error in (TimeoutError("read timed out"), HTTPError("https://example.com/bad", 403, "Forbidden", {}, io.BytesIO())):
            with self.subTest(error=type(error).__name__):
                open_url.reset_mock()
                open_url.side_effect = [error, self.response(ARTICLE)]
                producer = self.producer()
                with self.assertLogs("NewsProducer", level="INFO"):
                    producer.fetch_and_publish()
                self.assertEqual(open_url.call_count, 2)
                producer.producer.produce.assert_called_once()
                producer.producer.flush.assert_called_once_with(30)

    def test_invalid_timeout_fails_before_kafka_initialization(self):
        for timeout in ("0", "-1", "nan", "inf"):
            with patch.dict(os.environ, {"NEWS_RSS_TIMEOUT_SECONDS": timeout}), patch("news_producer.Producer") as kafka:
                with self.assertRaises(ValueError):
                    NewsKafkaProducer()
                kafka.assert_not_called()


if __name__ == "__main__":
    unittest.main()
