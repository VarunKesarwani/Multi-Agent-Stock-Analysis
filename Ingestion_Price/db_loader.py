"""Transactional, typed PostgreSQL upserts against the installed schema."""
from __future__ import annotations

import logging

import pandas as pd
from sqlalchemy import MetaData, Table, create_engine, select, text
from sqlalchemy.dialects.postgresql import insert

import config

logger = logging.getLogger(__name__)


def create_engine_from_url(connection_string=None):
    url = connection_string or config.POSTGRES_CONNECTION_STRING
    if not url:
        raise ValueError('Set POSTGRES_CONNECTION_STRING or pass --db-url')
    engine = create_engine(url, pool_size=config.DB_POOL_SIZE,
                           max_overflow=config.DB_MAX_OVERFLOW,
                           pool_timeout=config.DB_POOL_TIMEOUT,
                           pool_recycle=config.DB_POOL_RECYCLE, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
    except Exception:
        engine.dispose()
        raise
    return engine


class DatabaseManager:
    def __init__(self, connection_string=None):
        self.engine = create_engine_from_url(connection_string)
        self.metadata = MetaData()

    def close(self):
        self.engine.dispose()

    def _table(self, name):
        return Table(name, self.metadata, autoload_with=self.engine)

    def get_valid_symbols(self):
        table = self._table(config.TABLE_COMPANY_MASTER)
        with self.engine.connect() as connection:
            return set(connection.execute(select(table.c.SYMBOL)).scalars())

    def _upsert(self, df, table_name, keys, aliases=None):
        if df.empty:
            return 0
        table = self._table(table_name)
        frame = df.copy()
        # Support the existing equity DATE1 schema as well as the documented schema.
        renames = {name: alias for name, alias in (aliases or {}).items()
                   if name not in table.c and alias in table.c}
        frame = frame.rename(columns=renames)
        keys = [renames.get(key, key) for key in keys]
        missing = set(frame.columns) - set(table.c.keys())
        if missing:
            raise ValueError(f'{table_name} schema is incompatible; missing columns: {sorted(missing)}. '
                             'See Doc/PriceDataIngestion/VALIDATION_REVIEW.md before migrating.')
        frame = frame.dropna(subset=keys).drop_duplicates(subset=keys, keep='last')
        if frame.empty:
            return 0
        records = frame.astype(object).where(pd.notna(frame), None).to_dict('records')
        with self.engine.begin() as connection:
            for offset in range(0, len(records), 1000):
                statement = insert(table).values(records[offset:offset + 1000])
                updates = {name: statement.excluded[name] for name in frame.columns if name not in keys}
                statement = (statement.on_conflict_do_update(index_elements=keys, set_=updates)
                             if updates else statement.on_conflict_do_nothing(index_elements=keys))
                connection.execute(statement)
        logger.info('Upserted %s rows into %s', len(records), table_name)
        return len(records)

    def upsert_company_master(self, df):
        return self._upsert(df, config.TABLE_COMPANY_MASTER, ['SYMBOL'])

    def upsert_company_market(self, df):
        return self._upsert(df, config.TABLE_COMPANY_MARKET, ['SYMBOL'])

    def upsert_equity_bhavcopy(self, df):
        return self._upsert(df, config.TABLE_EQUITY_BHAVCOPY,
                            ['SYMBOL', 'SERIES', 'TRADE_DATE'],
                            {'TRADE_DATE': 'DATE1', 'TOTAL_TRADED_QTY': 'TTL_TRD_QNTY',
                             'DELIVERY_PERCENT': 'DELIV_PER', 'DELIVERY_QTY': 'DELIV_QTY'})

    def upsert_fo_bhavcopy(self, df):
        return self._upsert(df, config.TABLE_FO_BHAVCOPY,
                            ['INSTRUMENT', 'SYMBOL', 'EXPIRY_DATE', 'STRIKE_PRICE', 'OPTION_TYPE', 'TRADE_DATE'],
                            {'TRADE_DATE': 'DATE1'})
