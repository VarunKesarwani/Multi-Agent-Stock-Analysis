import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from transformers import transform_company_master, transform_equity, transform_fo, transform_screener_page, clean_numeric


@pytest.mark.parametrize('target,first', [
    ('2015-01-01', 'CM - Historical Archive'),
    ('2019-12-31', 'CM - Historical Archive'),
    ('2020-01-01', 'Full Bhavcopy and Security Deliverable data'),
])
def test_historical_source_order(target, first):
    from equity_ingestion import equity_source_labels
    labels = equity_source_labels(pd.Timestamp(target).date())
    assert labels[0] == first
    assert labels.index('CM - Historical Archive') == (0 if target < '2020-01-01' else 1)
    assert len(labels) == len(set(labels))


def test_historical_zip_headers_and_database_aliases():
    import io
    import zipfile
    from datetime import date
    from unittest.mock import MagicMock, patch
    from sqlalchemy import Column, MetaData, Table, Text, DateTime, Numeric, BigInteger
    import utils
    import db_loader
    source = next(s for s in config.EQUITY_SOURCES if s.label == 'CM - Historical Archive')
    assert utils.resolve_url(source.url, date(2015, 1, 1)) == (
        'https://nsearchives.nseindia.com/content/historical/EQUITIES/2015/JAN/cm01JAN2015bhav.csv.zip')
    # Actual header and first row from the downloaded 2015-01-01 archive.
    csv = 'SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,\n20MICRONS,EQ,30.45,31,30.25,30.4,30.4,30.6,37604,1150220.95,01-JAN-2015,200,INE144J01027,\n'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('cm01JAN2015bhav.csv', csv)
    result = transform_equity(utils.parse_csv_payload(buffer.getvalue()), source.label)
    row = result.iloc[0]
    assert row.TRADE_DATE == pd.Timestamp('2015-01-01')
    assert row.TURNOVER_LACS == pytest.approx(11.5022095)
    assert row.TOTAL_TRADED_QTY == 37604
    assert row.NO_OF_TRADES == 200
    assert pd.isna(row.DELIVERY_QTY) and pd.isna(row.DELIVERY_PERCENT)
    aliases = {'TRADE_DATE': 'DATE1', 'TOTAL_TRADED_QTY': 'TTL_TRD_QNTY',
               'DELIVERY_QTY': 'DELIV_QTY', 'DELIVERY_PERCENT': 'DELIV_PER'}
    columns = []
    for name in config.EQUITY_DB_COLUMNS:
        typ = Text if name in ('SYMBOL', 'SERIES') else DateTime if name == 'TRADE_DATE' else BigInteger if name in ('TOTAL_TRADED_QTY', 'NO_OF_TRADES', 'DELIVERY_QTY') else Numeric
        columns.append(Column(aliases.get(name, name), typ))
    table = Table('equity_bhavcopy', MetaData(), *columns)
    manager = db_loader.DatabaseManager.__new__(db_loader.DatabaseManager)
    manager.engine = MagicMock()
    with patch.object(manager, '_table', return_value=table):
        assert manager.upsert_equity_bhavcopy(result) == 1
    statement = manager.engine.begin.return_value.__enter__.return_value.execute.call_args.args[0]
    params = statement.compile().params
    assert params['TTL_TRD_QNTY_m0'] == 37604
    assert params['DELIV_QTY_m0'] is None


def test_equity_archive_failure_falls_back():
    from datetime import date
    from unittest.mock import Mock, patch
    import equity_ingestion
    target = date(2015, 1, 1)
    manager = Mock()
    transformed = pd.DataFrame({'SYMBOL': ['TCS']})
    with patch('equity_ingestion.utils.download_payload', side_effect=[(404, b''), (200, b'csv')]) as download, patch('equity_ingestion.utils.parse_csv_payload'), patch('equity_ingestion.transformers.transform_equity', return_value=transformed):
        assert equity_ingestion.ingest_equity(target, target, manager, Mock()) == []
    assert '/historical/EQUITIES/2015/JAN/cm01JAN2015bhav.csv.zip' in download.call_args_list[0].args[0]
    assert 'sec_bhavdata_full_01012015.csv' in download.call_args_list[1].args[0]
    manager.upsert_equity_bhavcopy.assert_called_once_with(transformed)


@pytest.mark.parametrize('label', ['CM - Bhavcopy', 'CM - Bhavcopy API Reports'])
def test_legacy_equity_date_prices_and_rupee_turnover(label):
    result = transform_equity(pd.DataFrame([dict(symbol=' tcs ', series='EQ', timestamp='2024-01-02',
        open=100, high=110, low=90, close=105, tottrdqty=1000, tottrdval=105000)]), label)
    assert list(result.columns) == config.EQUITY_DB_COLUMNS
    assert result.iloc[0].SYMBOL == 'TCS'
    assert result.iloc[0].TRADE_DATE == pd.Timestamp('2024-01-02')
    assert result.iloc[0].OPEN_PRICE == 100
    assert result.iloc[0].TURNOVER_LACS == 1.05
    assert result.iloc[0].TOTAL_TRADED_QTY == 1000


def test_full_equity_preserves_lakh_units_and_quantity():
    result = transform_equity(pd.DataFrame([dict(SYMBOL='TCS', SERIES='EQ', DATE1='03-Jan-2024',
        OPEN_PRICE=100, TTL_TRD_QNTY=2000, TURNOVER_LACS=2)]), 'Full Bhavcopy and Security Deliverable data')
    assert result.iloc[0].TOTAL_TRADED_QTY == 2000
    assert result.iloc[0].TURNOVER_LACS == 2
    assert result.iloc[0].OPEN_PRICE == 100


def test_udiff_equity_and_missing_keys():
    result = transform_equity(pd.DataFrame([dict(TckrSymb='TCS', SctySrs='EQ', TradDt='2024-01-04',
        TtlTrfVal=500000, TtlNbOfTxsExctd=50), dict(TckrSymb=None, TradDt='2024-01-04')]), 'CM-UDiFF Common Bhavcopy')
    assert len(result) == 1
    assert result.iloc[0].TURNOVER_LACS == 5
    assert result.iloc[0].NO_OF_TRADES == 50


def test_legacy_fo_preserves_fractional_strike_and_lakhs():
    result = transform_fo(pd.DataFrame([dict(INSTRUMENT='OPTSTK', SYMBOL='TCS', EXPIRY_DT='25-Jan-2024',
        STRIKE_PR=2500.5, OPTION_TYP='CE', TIMESTAMP='2024-01-04', VAL_INLAKH=20, CONTRACTS=10)]))
    assert len(result) == 1
    assert result.iloc[0].STRIKE_PRICE == 2500.5
    assert result.iloc[0].VAL_IN_LAKHS == 20


def test_udiff_fo_future_defaults_and_units():
    result = transform_fo(pd.DataFrame([dict(FinInstrmTp='STF', TckrSymb='TCS', XpryDt='2024-01-25',
        TradDt='2024-01-04', TtlTrfVal=500000, TtlTradgVol=20)]))
    assert result.iloc[0].INSTRUMENT == 'FUTSTK'
    assert result.iloc[0].STRIKE_PRICE == 0
    assert result.iloc[0].OPTION_TYPE == 'XX'
    assert result.iloc[0].VAL_IN_LAKHS == 5


def test_company_master_preserves_documented_fields():
    row = {'SYMBOL': ' tcs ', 'NAME OF COMPANY': 'TCS', 'PAID UP VALUE': 1,
           'MARKET LOT': 1, 'DATE OF LISTING': '2004-08-25'}
    result = transform_company_master(pd.DataFrame([row, row, {**row, 'SYMBOL': None}]))
    assert len(result) == 1
    assert result.iloc[0].PAID_UP_VALUE == 1
    assert result.iloc[0].MARKET_LOT == 1
    assert result.iloc[0].DATE_OF_LISTING == pd.Timestamp('2004-08-25')


def test_screener_abbreviated_headers_without_tbody():
    html = '<table class="data-table"><tr><th>Name</th><th>CMP Rs.</th><th>P/E</th><th>Mar Cap Rs.Cr.</th><th>Div Yld %</th><th>ROCE %</th></tr><tr><td><a href="/company/TCS/">TCS</a></td><td>1,234</td><td>-</td><td>500</td><td>2%</td><td>30</td></tr></table>'
    row = transform_screener_page(html)[0]
    assert row['CURRENT_MARKET_PRICE'] == 1234
    assert row['PE_RATIO'] is None
    assert row['MARKET_CAP_CR'] == 500
    assert row['DIVIDEND_YIELD'] == 2


@pytest.mark.parametrize('value', [None, float('nan'), float('inf'), '-', pd.NA])
def test_nonfinite_numbers_are_null(value):
    assert clean_numeric(value) is None
