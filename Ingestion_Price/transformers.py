"""Transformation routines for company master, screener, equity, and F&O data."""

from __future__ import annotations

import math
import logging
import re
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

NULL_EQUIVALENTS = {'', '-', '--', 'NA', 'N/A', 'na', 'n/a', None}


def normalize_string(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def normalize_symbol(value: Any) -> str | None:
    text = normalize_string(value)
    return text.upper() if text else None


def clean_numeric(value: Any) -> float | None:
    text = normalize_string(value)
    if text is None or text in NULL_EQUIVALENTS:
        return None
    text = re.sub(r'[,%₹$]', '', text)
    text = text.replace('%', '').strip()
    if text in NULL_EQUIVALENTS:
        return None
    try:
        number = float(text)
        return number if math.isfinite(number) else None
    except ValueError:
        return None


def clean_integer(value: Any) -> int | None:
    numeric = clean_numeric(value)
    if numeric is None:
        return None
    try:
        return int(numeric)
    except ValueError:
        return None


def clean_date(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        iso = isinstance(value, str) and re.match(r'^\d{4}-\d{2}-\d{2}', value)
        timestamp = pd.to_datetime(value, dayfirst=not bool(iso), errors='coerce')
        return timestamp if not pd.isna(timestamp) else None
    except Exception:
        return None


def transform_company_master(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized.columns = [str(col).strip().upper().replace(' ', '_') for col in df.columns]
    columns = ['SYMBOL', 'NAME_OF_COMPANY', 'SERIES', 'DATE_OF_LISTING',
               'PAID_UP_VALUE', 'MARKET_LOT', 'ISIN_NUMBER', 'FACE_VALUE']
    normalized = normalized.rename(columns={'COMPANY_NAME': 'NAME_OF_COMPANY'}).reindex(columns=columns)
    for col in ['NAME_OF_COMPANY', 'SERIES', 'ISIN_NUMBER']:
        normalized[col] = normalized[col].apply(normalize_string)
    normalized['SYMBOL'] = normalized['SYMBOL'].apply(normalize_symbol)
    normalized['DATE_OF_LISTING'] = normalized['DATE_OF_LISTING'].apply(clean_date)
    for col in ['PAID_UP_VALUE', 'FACE_VALUE']:
        normalized[col] = normalized[col].apply(clean_numeric)
    normalized['MARKET_LOT'] = normalized['MARKET_LOT'].apply(clean_integer)
    return normalized.dropna(subset=['SYMBOL', 'NAME_OF_COMPANY']).drop_duplicates('SYMBOL')


def _extract_symbol_from_link(href: str) -> str | None:
    if not href:
        return None
    match = re.search(r'/company/([^/]+)/', href)
    if not match:
        return None
    return normalize_symbol(match.group(1))


def transform_screener_page(html_content: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html_content, 'html.parser')
    table = soup.select_one('table.data-table')
    if table is None:
        logger.warning('Screener page missing .data-table')
        return []
    headers = [th.get_text(' ', strip=True).lower() for th in table.select('th')]
    rows = []
    for tr in table.select('tr'):
        cells = [td.get_text(strip=True) for td in tr.select('td')]
        if not cells:
            continue
        link = tr.select_one('a[href*=\"/company/\"]') or tr.select_one('a[href*="/company/"]')
        href = link['href'] if link and link.has_attr('href') else None
        symbol = _extract_symbol_from_link(href)
        if symbol is None:
            continue
        record: dict[str, Any] = {'SYMBOL': symbol}
        for column_name, key in [
            (('current market price', 'cmp'), 'CURRENT_MARKET_PRICE'),
            (('p/e',), 'PE_RATIO'),
            (('market cap', 'mar cap', 'm.cap'), 'MARKET_CAP_CR'),
            (('dividend yield', 'div yld', 'div yld.'), 'DIVIDEND_YIELD'),
            (('roce',), 'ROCE'),
        ]:
            try:
                index = next(i for i, header in enumerate(headers) if any(alias in header for alias in column_name))
                record[key] = clean_numeric(cells[index])
            except StopIteration:
                record[key] = None
            except IndexError:
                record[key] = None
        rows.append(record)
    return rows


def transform_screener_records(records: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(records)
    for column in config.COMPANY_MARKET_COLUMNS:
        if column not in df.columns:
            df[column] = None
    
    # Ensure numeric columns are properly typed
    numeric_columns = ['CURRENT_MARKET_PRICE', 'PE_RATIO', 'MARKET_CAP_CR', 'DIVIDEND_YIELD', 'ROCE']
    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors='coerce')
    
    return df[config.COMPANY_MARKET_COLUMNS].drop_duplicates(subset=['SYMBOL'])


def transform_nse_historical_json(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Transform NSE historical JSON 'data' array into equity bhavcopy DataFrame.

    Expected input: list of dicts with keys like `CH_SYMBOL`, `CH_SERIES`, `mTIMESTAMP`,
    `CH_PREVIOUS_CLS_PRICE`, `CH_OPENING_PRICE`, `CH_TRADE_HIGH_PRICE`,
    `CH_TRADE_LOW_PRICE`, `CH_LAST_TRADED_PRICE`, `CH_CLOSING_PRICE`, `VWAP`,
    `CH_TOT_TRADED_QTY`, `CH_TOT_TRADED_VAL`, `CH_TOTAL_TRADES`, `CH_TIMESTAMP`,
    `COP_DELIV_QTY`, `COP_DELIV_PERC`
    """
    if not records:
        return pd.DataFrame(columns=config.EQUITY_DB_COLUMNS)

    rows: list[dict[str, object]] = []
    for rec in records:
        try:
            symbol = normalize_symbol(rec.get('CH_SYMBOL'))
            series = normalize_string(rec.get('CH_SERIES'))
            # mTIMESTAMP is often like '31-Dec-2009' (day-month-year)
            trade_date = clean_date(rec.get('mTIMESTAMP')) or clean_date(rec.get('CH_TIMESTAMP'))
            prev_close = clean_numeric(rec.get('CH_PREVIOUS_CLS_PRICE'))
            open_price = clean_numeric(rec.get('CH_OPENING_PRICE'))
            high_price = clean_numeric(rec.get('CH_TRADE_HIGH_PRICE'))
            low_price = clean_numeric(rec.get('CH_TRADE_LOW_PRICE'))
            last_price = clean_numeric(rec.get('CH_LAST_TRADED_PRICE'))
            close_price = clean_numeric(rec.get('CH_CLOSING_PRICE'))
            total_qty = clean_integer(rec.get('CH_TOT_TRADED_QTY'))
            # Convert total traded value to lakhs to match existing TURNOVER_LACS semantics
            tot_traded_val = clean_numeric(rec.get('CH_TOT_TRADED_VAL'))
            turnover_lacs = None if tot_traded_val is None else (tot_traded_val / 100000.0)
            no_of_trades = clean_integer(rec.get('CH_TOTAL_TRADES'))
            delivery_qty = clean_integer(rec.get('COP_DELIV_QTY'))
            delivery_perc = clean_numeric(rec.get('COP_DELIV_PERC'))

            rows.append({
                'SYMBOL': symbol,
                'SERIES': series,
                'TRADE_DATE': trade_date,
                'OPEN_PRICE': open_price,
                'HIGH_PRICE': high_price,
                'LOW_PRICE': low_price,
                'CLOSE_PRICE': close_price,
                'LAST_PRICE': last_price,
                'PREV_CLOSE': prev_close,
                'TOTAL_TRADED_QTY': total_qty,
                'TURNOVER_LACS': turnover_lacs,
                'NO_OF_TRADES': no_of_trades,
                'DELIVERY_QTY': delivery_qty,
                'DELIVERY_PERCENT': delivery_perc,
            })
        except Exception:
            logger.exception('Failed to transform JSON record: %s', rec)
            continue

    df = pd.DataFrame(rows)

    # Ensure all expected columns exist
    for column in config.EQUITY_DB_COLUMNS:
        if column not in df.columns:
            df[column] = None

    # Cast numeric columns properly
    for column in [
        'OPEN_PRICE', 'HIGH_PRICE', 'LOW_PRICE', 'CLOSE_PRICE', 'LAST_PRICE',
        'PREV_CLOSE', 'TURNOVER_LACS', 'DELIVERY_PERCENT',
    ]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors='coerce')

    for column in ['TOTAL_TRADED_QTY', 'NO_OF_TRADES', 'DELIVERY_QTY']:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors='coerce').astype('Int64')

    # Ensure trade date is a Timestamp and drop rows without symbol or date
    df['TRADE_DATE'] = df['TRADE_DATE'].apply(lambda v: v if isinstance(v, pd.Timestamp) else clean_date(v))
    df = df.dropna(subset=['SYMBOL', 'TRADE_DATE'])

    return df[config.EQUITY_DB_COLUMNS].copy()


def _rename_source(df, aliases):
    normalized = df.copy()
    normalized.columns = [str(col).strip().upper() for col in df.columns]
    for target, sources in aliases.items():
        if target not in normalized:
            for source in sources:
                if source.upper() in normalized:
                    normalized[target] = normalized[source.upper()]
                    break
    return normalized


def transform_equity(df: pd.DataFrame, source_label: str) -> pd.DataFrame:
    aliases = {
        'SYMBOL': ['TckrSymb'], 'SERIES': ['SctySrs'],
        'TRADE_DATE': ['DATE1', 'TIMESTAMP', 'TRADED_DATE', 'TradDt'],
        'PREV_CLOSE': ['PREVCLOSE', 'PrvsClsgPric'],
        'OPEN_PRICE': ['OPEN', 'OpnPric'], 'HIGH_PRICE': ['HIGH', 'HghPric'],
        'LOW_PRICE': ['LOW', 'LwPric'], 'CLOSE_PRICE': ['CLOSE', 'ClsPric'],
        'LAST_PRICE': ['LAST', 'LastPric'],
        'TOTAL_TRADED_QTY': ['TTL_TRD_QNTY', 'TOTTRDQTY', 'TtlTradgVol'],
        'TURNOVER_LACS': ['TOTTRDVAL', 'TtlTrfVal'],
        'NO_OF_TRADES': ['TOTALTRADES', 'TtlNbOfTxsExctd', 'NoOfTrades'],
        'DELIVERY_QTY': ['DELIV_QTY', 'DelivQty'],
        'DELIVERY_PERCENT': ['DELIV_PER', 'DelivPer'],
    }
    source_columns = {str(col).strip().upper() for col in df.columns}
    normalized = _rename_source(df, aliases).reindex(columns=config.EQUITY_DB_COLUMNS)
    normalized['SYMBOL'] = normalized['SYMBOL'].apply(normalize_symbol)
    normalized['SERIES'] = normalized['SERIES'].apply(normalize_symbol)
    normalized['TRADE_DATE'] = normalized['TRADE_DATE'].apply(clean_date)
    for col in config.EQUITY_DB_COLUMNS:
        if col not in ('SYMBOL', 'SERIES', 'TRADE_DATE'):
            normalized[col] = normalized[col].apply(clean_numeric)
    if 'TURNOVER_LACS' not in source_columns and source_columns.intersection({'TOTTRDVAL', 'TTLTRFVAL'}):
        normalized['TURNOVER_LACS'] = normalized['TURNOVER_LACS'] / 100000
    for col in ['TOTAL_TRADED_QTY', 'NO_OF_TRADES', 'DELIVERY_QTY']:
        normalized[col] = pd.to_numeric(normalized[col], errors='coerce').astype('Int64')
    return normalized.dropna(subset=['SYMBOL', 'SERIES', 'TRADE_DATE']).drop_duplicates(
        ['SYMBOL', 'SERIES', 'TRADE_DATE'], keep='last')


def transform_fo(df: pd.DataFrame) -> pd.DataFrame:
    aliases = {target: [source] for target, source in config.FO_COLUMN_MAPPING.items()}
    aliases.update({
        'INSTRUMENT': ['FinInstrmTp', 'SctySrs'],
        'EXPIRY_DATE': ['EXPIRY_DT', 'XpryDt'], 'STRIKE_PRICE': ['STRIKE_PR', 'StrkPric'],
        'OPTION_TYPE': ['OPTION_TYP', 'OptnTp', 'OptType'],
        'TRADE_DATE': ['TIMESTAMP', 'DATE', 'TradDt'],
        'OPEN_PRICE': ['OPEN', 'OpnPric'], 'HIGH_PRICE': ['HIGH', 'HghPric'],
        'LOW_PRICE': ['LOW', 'LwPric'], 'CLOSE_PRICE': ['CLOSE', 'ClsPric'],
        'SETTLE_PRICE': ['SETTLE_PR', 'SttlmPric'],
        'CONTRACTS_TRADED': ['CONTRACTS', 'TtlTradgVol'],
        'VAL_IN_LAKHS': ['VAL_INLAKH', 'TtlTrfVal'],
        'OPEN_INTEREST': ['OPEN_INT', 'OpnIntrst'], 'CHANGE_IN_OI': ['CHG_IN_OI', 'ChngInOpnIntrst'],
    })
    source_columns = {str(col).strip().upper() for col in df.columns}
    normalized = _rename_source(df, aliases).reindex(columns=config.FO_DB_COLUMNS)
    for col in ['SYMBOL', 'INSTRUMENT', 'OPTION_TYPE']:
        normalized[col] = normalized[col].apply(normalize_symbol)
    normalized['INSTRUMENT'] = normalized['INSTRUMENT'].replace(
        {'STF': 'FUTSTK', 'STO': 'OPTSTK', 'IDF': 'FUTIDX', 'IDO': 'OPTIDX'})
    for col in ['TRADE_DATE', 'EXPIRY_DATE']:
        normalized[col] = normalized[col].apply(clean_date)
    for col in config.FO_DB_COLUMNS:
        if col not in ['SYMBOL', 'INSTRUMENT', 'OPTION_TYPE', 'TRADE_DATE', 'EXPIRY_DATE']:
            normalized[col] = normalized[col].apply(clean_numeric)
    futures = normalized['INSTRUMENT'].isin(['FUTSTK', 'FUTIDX'])
    normalized.loc[futures, 'STRIKE_PRICE'] = pd.to_numeric(normalized.loc[futures, 'STRIKE_PRICE'], errors='coerce').fillna(0)
    normalized.loc[futures, 'OPTION_TYPE'] = normalized.loc[futures, 'OPTION_TYPE'].fillna('XX')
    if 'TTLTRFVAL' in source_columns and not source_columns.intersection({'VAL_IN_LAKHS', 'VAL_INLAKH'}):
        normalized['VAL_IN_LAKHS'] = normalized['VAL_IN_LAKHS'] / 100000
    for col in ['CONTRACTS_TRADED', 'OPEN_INTEREST', 'CHANGE_IN_OI']:
        normalized[col] = pd.to_numeric(normalized[col], errors='coerce').astype('Int64')
    keys = ['INSTRUMENT', 'SYMBOL', 'EXPIRY_DATE', 'STRIKE_PRICE', 'OPTION_TYPE', 'TRADE_DATE']
    return normalized.dropna(subset=keys).drop_duplicates(keys, keep='last')
