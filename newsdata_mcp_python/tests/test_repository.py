from datetime import datetime, timezone

from newsdata_mcp.repository import NewsRepository


def test_build_filters_creates_exact_and_date_filters() -> None:
    filters = NewsRepository.build_filters(
        categories=["markets"], sources=["Reuters"], tones=["POSITIVE"], symbol="infy",
        published_after=datetime(2025, 1, 1, tzinfo=timezone.utc), published_before=None,
    )
    assert {"term": {"enrichment_status.keyword": "COMPLETED"}} in filters
    assert {"terms": {"category.keyword": ["markets"]}} in filters
    assert {"term": {"analysis.company_tones.symbol.keyword": "INFY"}} in filters
    assert any("range" in item for item in filters)

