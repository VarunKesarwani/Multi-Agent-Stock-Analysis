"""Command line orchestration for the ingestion pipeline."""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import sys
from datetime import date
from pathlib import Path

import db_loader
import equity_ingestion
import fo_ingestion
import company_master_ingestion
import screener_ingestion
import utils


def setup_logging() -> None:
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / 'ingestion.log', maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_handler.setFormatter(logging.Formatter('%(asctime)s | %(name)s | %(levelname)s | %(message)s'))
    logger.addHandler(file_handler)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter('%(asctime)s | %(name)s | %(levelname)s | %(message)s'))
    logger.addHandler(console_handler)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Ingestion pipeline for NSE market data')
    parser.add_argument('--skip-company-master', action='store_true', help='Skip company master ingestion')
    parser.add_argument('--skip-company-market', action='store_true', help='Skip company market data download')
    parser.add_argument('--skip-screener', action='store_true', help='Skip screener ingestion')
    parser.add_argument('--skip-equity', action='store_true', help='Skip equity ingestion')
    parser.add_argument('--skip-fo', action='store_true', help='Skip F&O ingestion')
    parser.add_argument('--db-url', type=str, default=None, help='Override database connection URL')
    parser.add_argument('--start-date', type=date.fromisoformat, default=date.today(), help='Equity start date YYYY-MM-DD')
    parser.add_argument('--end-date', type=date.fromisoformat, default=date.today(), help='Equity end date YYYY-MM-DD')
    parser.add_argument('--fo-start-date', type=date.fromisoformat, default=None, help='F&O start date YYYY-MM-DD')
    parser.add_argument('--fo-end-date', type=date.fromisoformat, default=None, help='F&O end date YYYY-MM-DD')
    args = parser.parse_args()
    args.fo_start_date = args.fo_start_date or date(date.today().year, 1, 1)
    args.fo_end_date = args.fo_end_date or date.today()
    if args.start_date > args.end_date or args.fo_start_date > args.fo_end_date:
        parser.error('Start date must not be after end date')
    return args


def main() -> int:
    setup_logging()
    logger = logging.getLogger(__name__)
    args = parse_arguments()

    logger.info('Starting ingestion pipeline')
    logger.info('skip-company-master=%s skip-company-market=%s skip-screener=%s skip-equity=%s skip-fo=%s',
                args.skip_company_master, args.skip_company_market, args.skip_screener, args.skip_equity, args.skip_fo)

    session = None
    manager = None
    failed = False
    try:
        manager = db_loader.DatabaseManager(args.db_url)
        session = utils.create_session()
        stages = [
            (args.skip_company_master, 'company master', lambda: company_master_ingestion.ingest_company_master(session, manager)),
            (args.skip_company_market or args.skip_screener, 'company market', lambda: screener_ingestion.ingest_screener(session, manager)),
            (args.skip_equity, 'equity', lambda: equity_ingestion.ingest_equity(args.start_date, args.end_date, manager, session)),
            (args.skip_fo, 'F&O', lambda: fo_ingestion.ingest_fo(args.fo_start_date, args.fo_end_date, manager, session)),
        ]
        for skipped, name, run in stages:
            if skipped:
                logger.info('%s ingestion skipped', name)
                continue
            try:
                result = run()
                if result is False or (isinstance(result, list) and result):
                    failed = True
                    logger.warning('%s ingestion incomplete: %s', name, result)
            except Exception:
                failed = True
                logger.exception('%s ingestion failed; continuing remaining stages', name)
        logger.info('Ingestion pipeline finished; failures=%s', failed)
        return int(failed)
    except Exception:
        logger.exception('Ingestion pipeline initialization failed')
        return 1
    finally:
        if session is not None:
            session.close()
        if manager is not None:
            manager.close()


if __name__ == '__main__':
    raise SystemExit(main())
