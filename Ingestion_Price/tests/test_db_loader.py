import sys
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest
from sqlalchemy import Column, MetaData, Table, String, Numeric, Date
from sqlalchemy.dialects import postgresql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db_loader import DatabaseManager


def manager_for(table):
    manager = DatabaseManager.__new__(DatabaseManager)
    manager._table = lambda _: table
    manager.engine = Mock()
    connection = Mock()
    context = Mock()
    context.__enter__ = Mock(return_value=connection)
    context.__exit__ = Mock(return_value=False)
    manager.engine.begin.return_value = context
    return manager, connection


def test_upsert_deduplicates_and_preserves_null_numeric_types():
    table = Table('company_market', MetaData(), Column('SYMBOL', String, primary_key=True), Column('PE_RATIO', Numeric))
    manager, connection = manager_for(table)
    assert manager.upsert_company_market(pd.DataFrame([{'SYMBOL':'TCS','PE_RATIO':5}, {'SYMBOL':'TCS','PE_RATIO':None}])) == 1
    compiled = connection.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert 'ON CONFLICT' in str(compiled)
    assert compiled.params['PE_RATIO_m0'] is None


def test_equity_legacy_date_alias():
    table = Table('equity_bhavcopy', MetaData(), Column('SYMBOL', String), Column('SERIES', String), Column('DATE1', Date))
    manager, connection = manager_for(table)
    manager.upsert_equity_bhavcopy(pd.DataFrame([{'SYMBOL':'TCS','SERIES':'EQ','TRADE_DATE':pd.Timestamp('2024-01-02')}]))
    statement = str(connection.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert '"DATE1"' in statement
    assert 'DO NOTHING' in statement


def test_incompatible_schema_fails_before_write():
    table = Table('fo_bhavcopy', MetaData(), Column('INSTRUMENT_NUMBER', String))
    manager, connection = manager_for(table)
    with pytest.raises(ValueError, match='schema is incompatible'):
        manager.upsert_fo_bhavcopy(pd.DataFrame([{'INSTRUMENT':'FUTSTK'}]))
    connection.execute.assert_not_called()
