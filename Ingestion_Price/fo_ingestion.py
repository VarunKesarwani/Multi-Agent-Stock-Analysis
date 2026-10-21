"""Futures & options data ingestion workflow."""

from __future__ import annotations

import logging
from datetime import date
from typing import List

import config
import db_loader
import transformers
import utils

logger = logging.getLogger(__name__)


def ingest_fo(
    start_date: date,
    end_date: date,
    db_manager: db_loader.DatabaseManager,
    session: 'requests.Session',
) -> List[date]:
    logger.info('Starting F&O ingestion from %s to %s', start_date, end_date)
    dates = utils.generate_trading_dates(start_date, end_date)
    failed_dates: List[date] = []
    for target_date in dates:
        logger.info('Processing F&O date %s', target_date)
        payload = None
        last_status_code = None
        for source in config.FO_SOURCES:
            url = utils.resolve_url(source.url, target_date)
            logger.info('Trying F&O source %s for %s', source.label, target_date)
            status_code, candidate_payload = utils.download_payload(url, session)
            last_status_code = status_code
            if status_code == 200 and candidate_payload:
                payload = candidate_payload
                logger.info('Downloaded F&O payload for %s from %s', target_date, source.label)
                break
            logger.warning(
                'F&O source unavailable for %s source=%s status=%s',
                target_date,
                source.label,
                status_code,
            )

        if not payload:
            logger.warning(
                'F&O payload unavailable for %s after %s source(s); last_status=%s',
                target_date,
                len(config.FO_SOURCES),
                last_status_code,
            )
            failed_dates.append(target_date)
            continue
        try:
            raw_df = utils.parse_csv_payload(payload)
            transformed = transformers.transform_fo(raw_df)
        except Exception:
            logger.exception('Failed to parse F&O payload for %s', target_date)
            failed_dates.append(target_date)
            continue
        if transformed.empty:
            logger.warning('Transformed F&O data empty for %s', target_date)
            failed_dates.append(target_date)
            continue
        try:
            db_manager.upsert_fo_bhavcopy(transformed)
        except Exception:
            logger.exception('F&O DB load failed for %s', target_date)
            failed_dates.append(target_date)
    logger.info('F&O ingestion finished with %s failed dates', len(failed_dates))
    return failed_dates

