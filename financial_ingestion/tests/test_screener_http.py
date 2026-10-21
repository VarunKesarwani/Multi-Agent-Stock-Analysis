from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import Mock

import pytest
import requests

from financial_ingestion import screener_http as http
from financial_ingestion.extractors import fetch_screener
from financial_ingestion.settings import Settings


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    waits = []
    def sleep(seconds):
        waits.append(seconds)
        now[0] += seconds
    monkeypatch.setattr(http.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(http.time, 'sleep', sleep)
    monkeypatch.setattr(http.random, 'uniform', lambda *_: 0.0)
    return now, waits


def response(status, retry_after=None):
    r = requests.Response()
    r.status_code = status
    r.url = 'https://www.screener.in/company/TCS/consolidated/'
    r._content = b'error'
    r._content_consumed = True
    if retry_after:
        r.headers['Retry-After'] = retry_after
    return r


def session(*results):
    s = requests.Session()
    s.get = Mock(side_effect=results)
    return s


def test_success_spacing_across_symbols(clock):
    s = session(response(200), response(200))
    http.get_screener_page(s, 'TCS', Settings())
    http.get_screener_page(s, 'ACC', Settings())
    assert clock[1] == [100]


def test_500_recovery_uses_backoff(clock):
    good = response(200)
    s = session(response(500), response(500), good)
    assert http.get_screener_page(s, 'TCS', Settings(screener_request_delay=15)) is good
    assert clock[1] == [30, 60]
    assert s.get.call_count == 3


@pytest.mark.parametrize('failure', [response(500), response(429), requests.Timeout(), requests.ConnectionError()])
def test_exhaustion_cools_down_next_symbol(clock, failure):
    s = session(failure, failure, failure, response(200))
    with pytest.raises(requests.RequestException):
        http.get_screener_page(s, 'TCS', Settings())
    http.get_screener_page(s, 'ACC', Settings())
    assert clock[1] == [100, 100, 300]
    assert s.get.call_count == 4


def test_retry_after_longer_than_cap_and_final_cooldown(clock):
    s = session(response(429, '600'), response(200))
    with pytest.raises(requests.HTTPError):
        http.get_screener_page(s, 'TCS', Settings(screener_max_attempts=1))
    http.get_screener_page(s, 'ACC', Settings())
    assert clock[1] == [600]


def test_retry_after_date_and_invalid_values():
    date = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=600))
    assert 598 <= http._retry_after(date) <= 600
    for invalid in ('bad', '-10', 'nan', 'inf', None):
        assert http._retry_after(invalid) == 0


@pytest.mark.parametrize('status', [401, 403, 400])
def test_permanent_errors_not_retried_or_fallback(clock, status):
    s = session(response(status))
    with pytest.raises(requests.HTTPError):
        fetch_screener(s, 'TCS')
    assert s.get.call_count == 1


def test_404_fallback_is_paced(clock, monkeypatch):
    good = response(200)
    good.url = 'https://www.screener.in/company/TCS/'
    s = session(response(404), good)
    monkeypatch.setattr('financial_ingestion.extractors.parse_screener', lambda *args: {'scope': 'STANDALONE'})
    assert fetch_screener(s, 'TCS')[0]['scope'] == 'STANDALONE'
    assert clock[1] == [100]
    assert s.get.call_args_list[1].args[0] == good.url


def test_500_never_falls_back(clock):
    s = session(response(500), response(500), response(500))
    with pytest.raises(requests.HTTPError):
        fetch_screener(s, 'TCS')
    assert all(c.args[0].endswith('/consolidated/') for c in s.get.call_args_list)


def test_configuration_from_environment(monkeypatch):
    monkeypatch.setattr('financial_ingestion.settings.load_dotenv', lambda *a, **k: None)
    monkeypatch.setenv('SCREENER_REQUEST_DELAY_SECONDS', '100')
    monkeypatch.setenv('SCREENER_MAX_ATTEMPTS', '2')
    cfg = Settings.from_env()
    assert cfg.screener_request_delay == 100
    assert cfg.screener_max_attempts == 2


@pytest.mark.parametrize('kwargs', [
    {'screener_request_delay': 0}, {'screener_request_delay': float('nan')},
    {'screener_request_jitter': -1}, {'screener_max_attempts': 0},
    {'screener_max_attempts': 11}, {'screener_max_backoff': 1},
])
def test_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)
