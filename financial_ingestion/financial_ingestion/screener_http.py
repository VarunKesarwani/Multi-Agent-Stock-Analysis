"""Paced Screener GETs for a single sequential producer using a shared Session."""

import logging
import math
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

from .settings import Settings

LOG = logging.getLogger(__name__)
RETRYABLE = {429, 500, 502, 503, 504}


def _retry_after(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        seconds = float(value)
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            seconds = (date - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return 0.0
    return max(0.0, seconds) if math.isfinite(seconds) else 0.0


def _defer(session: requests.Session, seconds: float) -> None:
    # Keep the deadline on the shared session, including across symbols and
    # after the final failed attempt. A new Session starts a new pacing window.
    session._screener_next_request_at = max(
        getattr(session, '_screener_next_request_at', 0.0),
        time.monotonic() + seconds,
    )


def get_screener_page(
    session: requests.Session, url: str, settings: Settings
) -> requests.Response:
    """GET with spacing, bounded transient retries and a cross-symbol cooldown.

    Reuse one Session for the complete sequential run. Do not configure extra
    HTTPAdapter retries: this function owns the retry budget and pacing.
    """
    for attempt in range(1, settings.screener_max_attempts + 1):
        wait = max(0.0, getattr(session, '_screener_next_request_at', 0.0) - time.monotonic())
        if wait:
            LOG.info('Screener waiting %.1fs before %s', wait, url)
            time.sleep(wait)
        response = None
        try:
            response = session.get(url, timeout=45)
        except (requests.Timeout, requests.ConnectionError):
            if attempt == settings.screener_max_attempts:
                _defer(session, settings.screener_failure_cooldown)
                raise
            LOG.warning('Screener network failure for %s (attempt %s/%s)',
                        url, attempt, settings.screener_max_attempts)
        finally:
            _defer(session, settings.screener_request_delay +
                   random.uniform(0, settings.screener_request_jitter))

        if response is not None and response.status_code not in RETRYABLE:
            # The caller handles 404-only standalone fallback and other errors.
            return response

        retry_after = _retry_after(response.headers.get('Retry-After')) if response is not None else 0.0
        delay = max(retry_after, min(settings.screener_max_backoff,
                    settings.screener_backoff * 2 ** (attempt - 1)) +
                    random.uniform(0, settings.screener_request_jitter))
        _defer(session, delay)
        if response is not None:
            LOG.warning('Screener HTTP %s for %s (attempt %s/%s)',
                        response.status_code, url, attempt, settings.screener_max_attempts)
            if attempt == settings.screener_max_attempts:
                _defer(session, settings.screener_failure_cooldown)
                response.close()
                response.raise_for_status()
            response.close()
    raise RuntimeError('Screener retry budget exhausted')
