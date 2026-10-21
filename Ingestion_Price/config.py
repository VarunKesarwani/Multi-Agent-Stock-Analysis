"""Central ingestion configuration and source metadata."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class SourceURL:
    label: str
    url: str


POSTGRES_CONNECTION_STRING: Final[str] = os.getenv('POSTGRES_CONNECTION_STRING', '')

COMPANY_MASTER_URL: Final[str] = (
    'https://archives.nseindia.com/content/equities/EQUITY_L.csv'
)

COMPANY_MARKET_URL: Final[str] = (
    'https://www.screener.in/screens/599148/companies-by-market-cap/?page={page}'
)

EQUITY_SOURCES: Final[list[SourceURL]] = [
    SourceURL(
        label='Full Bhavcopy and Security Deliverable data',
        url='https://archives.nseindia.com/products/content/sec_bhavdata_full_{date_ddmmyyyy}.csv',
    ),
    SourceURL(
        label='CM - Historical Archive',
        url=(
            'https://nsearchives.nseindia.com/content/historical/EQUITIES/'
            '{year}/{month}/cm{date_ddMMMyyyy}bhav.csv.zip'
        ),
    ),
    SourceURL(
        label='CM - Bhavcopy',
        url=(
            'https://archives.nseindia.com/api/reports?archives='
            '[{"name":"CM - Bhavcopy(csv)","type":"archives","category":"capital-market","section":"equities"}]'
            '&date={Date}&type=equities&mode=single'
        ),
    ),
    SourceURL(
        label='CM-UDiFF Common Bhavcopy',
        url=(
            'https://archives.nseindia.com/api/reports?archives='
            '[{"name":"CM-UDiFF Common Bhavcopy Final (zip)","type":"daily-reports","category":"capital-market","section":"equities"}]'
            '&date={Date}&type=equities&mode=single'
        ),
    ),
]

# NSE discontinued legacy CSV bhavcopy reports on 8 July 2024.
# Keep sources CSV-only: legacy _zip.zip archives contain DBF/DAT files.
FO_SOURCES: Final[list[SourceURL]] = [
    SourceURL(
        label='F&O - UDiFF Common Bhavcopy Final',
        url=(
            'https://archives.nseindia.com/content/fo/'
            'BhavCopy_NSE_FO_0_0_0_{date_yyyymmdd}_F_0000.csv.zip'
        ),
    ),
    SourceURL(
        label='F&O - UDiFF Common Bhavcopy Final (alternate archive host)',
        url=(
            'https://nsearchives.nseindia.com/content/fo/'
            'BhavCopy_NSE_FO_0_0_0_{date_yyyymmdd}_F_0000.csv.zip'
        ),
    ),
    SourceURL(
        label='F&O - Legacy CSV Bhavcopy',
        url=(
            'https://archives.nseindia.com/content/historical/DERIVATIVES/'
            '{year}/{month}/fo{date_ddMMMyyyy}bhav.csv.zip'
        ),
    ),
]

# Backward-compatible alias for callers that still expect a single source.
FO_SOURCE: Final[SourceURL] = FO_SOURCES[0]

DEFAULT_HEADERS: Final[dict[str, str]] = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/125.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
}

EXTENDED_HEADERS: Final[dict[str, str]] = {
    **DEFAULT_HEADERS,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Referer': 'https://www.nseindia.com',
    'Connection': 'keep-alive',
}

REQUEST_TIMEOUT: Final[int] = 60
RETRY_TOTAL: Final[int] = 3
RETRY_BACKOFF_FACTOR: Final[float] = 1.0
RETRY_STATUS_FORCELIST: Final[list[int]] = [429, 500, 502, 503, 504]
RATE_LIMIT_DELAY_SECONDS: Final[float] = 1.5
HTTP_POOL_CONNECTIONS: Final[int] = 10
HTTP_POOL_MAXSIZE: Final[int] = 10
DB_POOL_SIZE: Final[int] = 5
DB_MAX_OVERFLOW: Final[int] = 10
DB_POOL_TIMEOUT: Final[int] = 30
DB_POOL_RECYCLE: Final[int] = 1800

TABLE_COMPANY_MASTER: Final[str] = 'company_master'
TABLE_COMPANY_MARKET: Final[str] = 'company_market'
TABLE_EQUITY_BHAVCOPY: Final[str] = 'equity_bhavcopy'
TABLE_FO_BHAVCOPY: Final[str] = 'fo_bhavcopy'

COMPANY_MARKET_COLUMNS: Final[list[str]] = [
    'SYMBOL',
    'CURRENT_MARKET_PRICE',
    'PE_RATIO',
    'MARKET_CAP_CR',
    'DIVIDEND_YIELD',
    'ROCE',
]

# Columns that should be treated as numeric when cleaning/casting scraped data.
COMPANY_MARKET_NUMERIC_COLUMNS: Final[list[str]] = [
    'CURRENT_MARKET_PRICE',
    'PE_RATIO',
    'MARKET_CAP_CR',
    'DIVIDEND_YIELD',
    'ROCE',
]

# Default values applied when transforming scraped rows. Keys are canonical column names.
COMPANY_MARKET_DEFAULTS: Final[dict[str, object]] = {
    'SYMBOL': '',
    'CURRENT_MARKET_PRICE': 0.0,
    'PE_RATIO': None,
    'MARKET_CAP_CR': 0.0,
    'DIVIDEND_YIELD': None,
    'ROCE': None,
}

# Numeric rounding precision used by transformers when rounding numeric columns.
DECIMAL_PRECISION: Final[int] = 2

EQUITY_DB_COLUMNS: Final[list[str]] = [
    'SYMBOL',
    'SERIES',
    'TRADE_DATE',
    'OPEN_PRICE',
    'HIGH_PRICE',
    'LOW_PRICE',
    'CLOSE_PRICE',
    'LAST_PRICE',
    'PREV_CLOSE',
    'TOTAL_TRADED_QTY',
    'TURNOVER_LACS',
    'NO_OF_TRADES',
    'DELIVERY_QTY',
    'DELIVERY_PERCENT',
]

FO_DB_COLUMNS: Final[list[str]] = [
    'INSTRUMENT',
    'SYMBOL',
    'EXPIRY_DATE',
    'STRIKE_PRICE',
    'OPTION_TYPE',
    'TRADE_DATE',
    'OPEN_PRICE',
    'HIGH_PRICE',
    'LOW_PRICE',
    'CLOSE_PRICE',
    'SETTLE_PRICE',
    'CONTRACTS_TRADED',
    'VAL_IN_LAKHS',
    'OPEN_INTEREST',
    'CHANGE_IN_OI',
]

CM_BHAVCOPY_MAPPING: Final[dict[str, str]] = {
    'SYMBOL': 'SYMBOL',
    'SERIES': 'SERIES',
    'DATE1': 'TRADE_DATE',
    'PREV_CLOSE': 'PREV_CLOSE',
    'OPEN_PRICE': 'OPEN',
    'HIGH_PRICE': 'HIGH',
    'LOW_PRICE': 'LOW',
    'LAST_PRICE': 'LAST',
    'CLOSE_PRICE': 'CLOSE',
    'TOTAL_TRADED_QTY': 'TOTTRDQTY',
    'TURNOVER_LACS': 'TOTTRDVAL',
    'NO_OF_TRADES': 'NO_OF_TRADES',
    'DELIVERY_QTY': 'DELIV_QTY',
    'DELIVERY_PERCENT': 'DELIV_PER',
}

CM_UDIFF_BHAVCOPY_MAPPING: Final[dict[str, str]] = {
    'SYMBOL': 'TckrSymb',
    'SERIES': 'SctySrs',
    'DATE1': 'TradDt',
    'PREV_CLOSE': 'PrvsClsgPric',
    'OPEN_PRICE': 'OpnPric',
    'HIGH_PRICE': 'HghPric',
    'LOW_PRICE': 'LwPric',
    'LAST_PRICE': 'LastPric',
    'CLOSE_PRICE': 'ClsPric',
    'TOTAL_TRADED_QTY': 'TtlTradgVol',
    'TURNOVER_LACS': 'TtlTrfVal',
    'NO_OF_TRADES': 'NoOfTrades',
    'DELIVERY_QTY': 'DelivQty',
    'DELIVERY_PERCENT': 'DelivPer',
}

FO_COLUMN_MAPPING: Final[dict[str, str]] = {
    'INSTRUMENT': 'FinInstrmNm',
    'SYMBOL': 'TckrSymb',
    'EXPIRY_DATE': 'XpryDt',
    'STRIKE_PRICE': 'StrkPric',
    'OPTION_TYPE': 'OptType',
    'TRADE_DATE': 'TradDt',
    'OPEN_PRICE': 'OpnPric',
    'HIGH_PRICE': 'HghPric',
    'LOW_PRICE': 'LwPric',
    'CLOSE_PRICE': 'ClsPric',
    'SETTLE_PRICE': 'SttlmPric',
    'CONTRACTS_TRADED': 'TtlTradgVol',
    'VAL_IN_LAKHS': 'TtlTrfVal',
    'OPEN_INTEREST': 'OpnIntrst',
    'CHANGE_IN_OI': 'ChngInOpnIntrst',
}

