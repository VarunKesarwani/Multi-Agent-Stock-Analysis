"""Screener.in market data ingestion workflow."""

from __future__ import annotations

import logging
import time

import config
import db_loader
import transformers
import utils

logger = logging.getLogger(__name__)


def _fetch_page(session: 'requests.Session', page: int) -> tuple[int, str]:
    url = config.COMPANY_MARKET_URL.format(page=page)
    status_code, content = utils.download_payload(url, session)
    if status_code != 200 or not content:
        return status_code, ''
    return status_code, content.decode('utf-8', errors='replace')


def ingest_screener(session: 'requests.Session', db_manager: db_loader.DatabaseManager) -> bool:
    logger.info('Starting screener ingestion')
    valid_symbols = db_manager.get_valid_symbols()
    if not valid_symbols:
        logger.warning('No valid symbols available for screener ingestion')
        return False
    page = 1
    total_upserted = 0
    while True:
        logger.info('Fetching screener page %s', page)
        status_code, html = _fetch_page(session, page)
        if status_code not in (200, 404):
            logger.error('Screener HTTP failure: %s', status_code)
            return False
        if status_code == 404 or not html:
            logger.info('Stopping screener ingestion at page %s', page)
            break
        records = transformers.transform_screener_page(html)
        if not records:
            logger.info('No records found on page %s', page)
            break
        filtered_records = [record for record in records if record.get('SYMBOL') in valid_symbols]
        if not filtered_records:
            logger.info('No matching symbols on page %s; continuing', page)
            page += 1
            time.sleep(config.RATE_LIMIT_DELAY_SECONDS)
            continue
        df = transformers.transform_screener_records(filtered_records)
        if df.empty:
            logger.warning('No valid screener rows after transformation on page %s', page)
            break
        db_manager.upsert_company_market(df)
        total_upserted += len(df)
        logger.info('Upserted %s screener rows from page %s', len(df), page)
        page += 1
        time.sleep(config.RATE_LIMIT_DELAY_SECONDS)
    logger.info('Screener ingestion completed total_upserted=%s', total_upserted)
    return True

