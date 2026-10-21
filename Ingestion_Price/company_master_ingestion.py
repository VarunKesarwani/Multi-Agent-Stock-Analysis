"""Company master ingestion workflow."""

from __future__ import annotations

import logging

import requests

import config
import db_loader
import transformers
import utils

logger = logging.getLogger(__name__)


def ingest_company_master(session: requests.Session, db_manager: db_loader.DatabaseManager) -> bool:
    logger.info('Starting company master ingestion')
    status_code, payload = utils.download_payload(config.COMPANY_MASTER_URL, session)
    if status_code != 200 or not payload:
        logger.error('Failed to download company master, status=%s', status_code)
        return False
    try:
        raw_df = utils.parse_csv_payload(payload)
    except Exception:
        logger.exception('Failed to parse company master payload')
        return False
    transformed = transformers.transform_company_master(raw_df)
    if transformed.empty:
        logger.warning('Transformed company master is empty')
        return False
    db_manager.upsert_company_master(transformed)
    logger.info('Company master ingestion completed rows=%s', len(transformed))
    return True
