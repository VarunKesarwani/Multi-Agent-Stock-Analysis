import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as ingestion_main


def test_parse_arguments_supports_skip_company_market(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['main.py', '--skip-company-market'])

    args = ingestion_main.parse_arguments()

    assert args.skip_company_market is True


from datetime import date
from unittest.mock import Mock
import pytest
import equity_ingestion
import screener_ingestion


def test_fo_default_dates_and_argument_order(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['main.py', '--skip-company-master', '--skip-equity', '--skip-company-market'])
    manager, session = Mock(), Mock()
    monkeypatch.setattr(ingestion_main, 'setup_logging', lambda: None)
    monkeypatch.setattr(ingestion_main.db_loader, 'DatabaseManager', lambda _: manager)
    monkeypatch.setattr(ingestion_main.utils, 'create_session', lambda: session)
    run = Mock(return_value=[])
    monkeypatch.setattr(ingestion_main.fo_ingestion, 'ingest_fo', run)
    assert ingestion_main.main() == 0
    run.assert_called_once_with(date(date.today().year, 1, 1), date.today(), manager, session)
    session.close.assert_called_once()
    manager.close.assert_called_once()


def test_reversed_dates_rejected(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['main.py', '--start-date', '2024-02-01', '--end-date', '2024-01-01'])
    with pytest.raises(SystemExit):
        ingestion_main.parse_arguments()


def test_equity_download_failure_is_reported(monkeypatch):
    monkeypatch.setattr(equity_ingestion.utils, 'download_payload', lambda *args: (404, b''))
    day = date(2024, 1, 2)
    assert equity_ingestion.ingest_equity(day, day, Mock(), Mock()) == [day]


def test_screener_continues_after_unmatched_page(monkeypatch):
    pages = iter([(200, 'one'), (200, 'two'), (404, '')])
    monkeypatch.setattr(screener_ingestion, '_fetch_page', lambda *args: next(pages))
    monkeypatch.setattr(screener_ingestion.transformers, 'transform_screener_page',
                        lambda html: [{'SYMBOL': 'UNKNOWN' if html == 'one' else 'TCS'}])
    monkeypatch.setattr(screener_ingestion.time, 'sleep', lambda _: None)
    manager = Mock()
    manager.get_valid_symbols.return_value = {'TCS'}
    assert screener_ingestion.ingest_screener(Mock(), manager)
    manager.upsert_company_market.assert_called_once()
