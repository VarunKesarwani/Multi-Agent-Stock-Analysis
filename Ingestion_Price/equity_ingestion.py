"""Equity bhavcopy ingestion workflow."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import List

import config
import db_loader
import transformers
import utils
import requests

logger = logging.getLogger(__name__)


def equity_source_labels(target_date: date) -> list[str]:
    labels = [source.label for source in config.EQUITY_SOURCES]
    if target_date < date(2020, 1, 1):
        labels.remove('CM - Historical Archive')
        labels.insert(0, 'CM - Historical Archive')
    return labels + ['CM - Bhavcopy API Reports']


def ingest_equity(
    start_date: date,
    end_date: date,
    db_manager: db_loader.DatabaseManager,
    session: 'requests.Session',
) -> List[date]:
    logger.info('Starting equity ingestion from %s to %s', start_date, end_date)
    dates = utils.generate_trading_dates(start_date, end_date)
    failed_dates: List[date] = []
    source_map = {source.label: source for source in config.EQUITY_SOURCES}
    for target_date in dates:
        logger.info('Processing equity date %s', target_date)
        success = False
        for label in equity_source_labels(target_date):
            # Special handling for API Reports endpoint
            if label == 'CM - Bhavcopy API Reports':
                # Format date as DD-Mon-YYYY for API endpoint (e.g., 02-Jan-2019)
                date_str = target_date.strftime('%d-%b-%Y')
                url = f"https://www.nseindia.com/api/reports?archives=%5B%7B%22name%22%3A%22CM%20-%20Bhavcopy(csv)%22%2C%22type%22%3A%22archives%22%2C%22category%22%3A%22capital-market%22%2C%22section%22%3A%22equities%22%7D%5D&date={date_str}&type=equities&mode=single"
            else:
                source = source_map[label]
                url = utils.resolve_url(source.url, target_date)
            
            status_code, payload = utils.download_payload(url, session)
            # Handle 404 errors gracefully - log with timestamp and continue
            if status_code == 404:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                logger.error('[%s] 404 Error: URL not found for equity source %s on %s. URL: %s', timestamp, label, target_date, url)
                continue
            if status_code != 200 or not payload:
                logger.warning('Equity source %s failed for %s status=%s', label, target_date, status_code)
                continue
            try:
                raw_df = utils.parse_csv_payload(payload)
                transformed = transformers.transform_equity(raw_df, label)
            except Exception:
                logger.exception('Failed to parse equity payload for %s from %s', target_date, label)
                continue
            if transformed.empty:
                logger.warning('Transformed equity data empty for %s using %s', target_date, label)
                continue
            try:
                db_manager.upsert_equity_bhavcopy(transformed)
                logger.info('Loaded equity data for %s rows=%s', target_date, len(transformed))
                success = True
                break
            except Exception:
                logger.exception('Equity DB load failed for %s using %s', target_date, label)
        if not success:
            failed_dates.append(target_date)
    logger.info('Equity ingestion finished with %s failed dates', len(failed_dates))
    return failed_dates
