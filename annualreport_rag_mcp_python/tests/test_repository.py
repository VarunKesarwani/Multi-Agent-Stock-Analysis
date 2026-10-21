from __future__ import annotations

from types import SimpleNamespace

import pytest

from annualreport_rag_mcp.repository import AnnualReportRepository, _match_filter


class FakeEmbedder:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.queries.append(text)
        return [0.1, 0.2, 0.3]


class FakeQdrant:
    def __init__(self) -> None:
        self.kwargs = {}

    def query_points(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(points=[SimpleNamespace(
            id="stable-id",
            score=0.91234567,
            payload={
                "text": "Revenue increased during the year.",
                "symbol": "TATASTEEL",
                "year": "2025",
                "source_file": "TATASTEEL_2025.md",
                "original_chunk_id": 7,
                "chunk_part": 2,
                "chunk_part_count": 3,
                "heading": "Financial performance",
            },
        )])


def test_search_uses_same_embedding_and_returns_citation():
    qdrant = FakeQdrant()
    embedder = FakeEmbedder()
    repository = AnnualReportRepository(qdrant, embedder, "annual_reports", max_results=20)

    results = repository.search(
        query="revenue growth",
        symbol="TATASTEEL",
        year=2025,
        document_type=None,
        limit=8,
        min_score=0.5,
    )

    assert embedder.queries == ["revenue growth"]
    assert qdrant.kwargs["collection_name"] == "annual_reports"
    assert qdrant.kwargs["query"] == [0.1, 0.2, 0.3]
    assert qdrant.kwargs["limit"] == 8
    assert qdrant.kwargs["score_threshold"] == 0.5
    assert results[0]["score"] == 0.912346
    assert results[0]["citation"]["id"] == "TATASTEEL_2025.md#chunk-7-part-2"
    assert results[0]["citation"]["section"] == "Financial performance"
    assert "text" not in results[0]["metadata"]


def test_year_filter_accepts_string_and_integer_payloads():
    query_filter = _match_filter("TATASTEEL", "2025", None)
    year_filter = query_filter.must[1]

    assert [condition.key for condition in year_filter.should] == ["year", "year"]
    assert [condition.match.value for condition in year_filter.should] == ["2025", 2025]


def test_blank_or_oversized_query_is_rejected_before_embedding():
    repository = AnnualReportRepository(FakeQdrant(), FakeEmbedder(), "annual_reports")
    common = dict(symbol="TATASTEEL", year=None, document_type=None, limit=8, min_score=None)

    with pytest.raises(ValueError, match="blank"):
        repository.search(query="   ", **common)
    with pytest.raises(ValueError, match="2000"):
        repository.search(query="x" * 2_001, **common)


def test_limit_is_capped_by_repository_setting():
    qdrant = FakeQdrant()
    repository = AnnualReportRepository(qdrant, FakeEmbedder(), "annual_reports", max_results=5)

    repository.search(
        query="risk factors", symbol="TATASTEEL", year=None, document_type=None, limit=20, min_score=None
    )

    assert qdrant.kwargs["limit"] == 5
