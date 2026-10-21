"""Compatibility entry point for the canonical Screener market ingestion."""
from screener_ingestion import ingest_screener


def ingest_company_market(session, db_manager) -> bool:
    return ingest_screener(session, db_manager)
