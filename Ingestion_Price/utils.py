"""HTTP and parsing utilities for the ingestion pipeline."""

from __future__ import annotations

import io
import logging
import zipfile
from datetime import date, timedelta

import pandas as pd
import requests
from requests.adapters import HTTPAdapter, Retry

import config

logger = logging.getLogger(__name__)


def create_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=config.RETRY_TOTAL,
        backoff_factor=config.RETRY_BACKOFF_FACTOR,
        status_forcelist=config.RETRY_STATUS_FORCELIST,
        allowed_methods={'GET', 'POST'},
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=config.HTTP_POOL_CONNECTIONS,
        pool_maxsize=config.HTTP_POOL_MAXSIZE,
    )
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    session.headers.update(config.EXTENDED_HEADERS)
    try:
        session.get(config.COMPANY_MASTER_URL, timeout=config.REQUEST_TIMEOUT)
        logger.info('Initialized HTTP session with NSE homepage')
    except requests.RequestException as exc:
        logger.warning('Could not warm up HTTP session: %s', exc)
    return session


def resolve_url(template: str, target_date: date) -> str:
    url = template
    url = url.replace('{date_yyyymmdd}', target_date.strftime('%Y%m%d'))
    url = url.replace('{Date}', target_date.strftime('%d-%b-%Y'))
    url = url.replace('{date_ddmmyyyy}', target_date.strftime('%d%m%Y'))
    url = url.replace('{date_ddMMMyyyy}', target_date.strftime('%d%b%Y').upper())
    url = url.replace('{year}', target_date.strftime('%Y'))
    url = url.replace('{month}', target_date.strftime('%b').upper())
    return url


def generate_trading_dates(start_date: date, end_date: date) -> list[date]:
    if start_date > end_date:
        raise ValueError("Start date must not be after end date")
    dates: list[date] = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def download_payload(url: str, session: requests.Session) -> tuple[int, bytes]:
    try:
        response = session.get(url, timeout=config.REQUEST_TIMEOUT)
        response.raise_for_status()
        logger.debug('Downloaded payload %s status=%s', url, response.status_code)
        return response.status_code, response.content
    except requests.RequestException as exc:
        status_code = exc.response.status_code if getattr(exc, 'response', None) is not None else 0
        logger.warning('Download failed %s status=%s error=%s', url, status_code, exc)
        return status_code, b''


def parse_csv_payload(payload: bytes) -> pd.DataFrame:
    if zipfile.is_zipfile(io.BytesIO(payload)):
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            members = [m for m in zf.infolist() if m.filename.lower().endswith('.csv')]
            if not members:
                raise ValueError('ZIP archive contains no CSV file')
            with zf.open(members[0]) as content_file:
                decoded = content_file.read().decode('utf-8', errors='replace')
    else:
        decoded = payload.decode('utf-8', errors='replace')
    dataframe = pd.read_csv(io.StringIO(decoded), low_memory=False)
    logger.info('Parsed payload rows=%s', len(dataframe))
    return dataframe

