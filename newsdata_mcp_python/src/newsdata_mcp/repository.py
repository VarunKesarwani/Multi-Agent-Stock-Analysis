from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from elasticsearch import AsyncElasticsearch

KEYWORD_FIELDS = {
    "category": "category.keyword",
    "source": "source.keyword",
    "status": "enrichment_status.keyword",
    "tone": "analysis.overall_tone.keyword",
    "symbol": "analysis.company_tones.symbol.keyword",
}


class NewsRepository:
    def __init__(self, client: AsyncElasticsearch, index: str, max_results: int = 200) -> None:
        self.client = client
        self.index = index
        self.max_results = max_results

    @classmethod
    def connect(
        cls, *, url: str, index: str, username: str | None, password: str | None,
        api_key: str | None, verify_certs: bool, max_results: int,
    ) -> "NewsRepository":
        options: dict[str, Any] = {"verify_certs": verify_certs, "request_timeout": 15}
        if api_key:
            options["api_key"] = api_key
        elif username and password:
            options["basic_auth"] = (username, password)
        return cls(AsyncElasticsearch(url, **options), index, max_results)

    def _limit(self, value: int) -> int:
        if value < 1:
            raise ValueError("limit must be positive")
        return min(value, self.max_results)

    @staticmethod
    def build_filters(
        *, categories: list[str] | None = None, sources: list[str] | None = None,
        tones: list[str] | None = None, symbol: str | None = None,
        published_after: datetime | None = None, published_before: datetime | None = None,
    ) -> list[dict[str, Any]]:
        filters: list[dict[str, Any]] = [{"term": {KEYWORD_FIELDS["status"]: "COMPLETED"}}]
        for values, field in ((categories, "category"), (sources, "source"), (tones, "tone")):
            if values:
                filters.append({"terms": {KEYWORD_FIELDS[field]: values}})
        if symbol:
            filters.append({"term": {KEYWORD_FIELDS["symbol"]: symbol.upper()}})
        if published_after or published_before:
            bounds: dict[str, str] = {}
            if published_after:
                bounds["gte"] = published_after.isoformat()
            if published_before:
                bounds["lte"] = published_before.isoformat()
            filters.append({"range": {"published_at": bounds}})
        return filters

    async def ping(self) -> bool:
        return bool(await self.client.ping())

    async def search_news(
        self, *, query: str | None, categories: list[str] | None, sources: list[str] | None,
        tones: list[str] | None, symbol: str | None, published_after: datetime | None,
        published_before: datetime | None, limit: int,
    ) -> dict[str, Any]:
        must = [{"multi_match": {"query": query, "fields": ["title^3", "summary", "analysis.summary^2"]}}] if query else []
        body = {
            "query": {"bool": {"must": must, "filter": self.build_filters(
                categories=categories, sources=sources, tones=tones, symbol=symbol,
                published_after=published_after, published_before=published_before)}},
            "sort": [{"published_at": {"order": "desc", "unmapped_type": "date"}}],
            "size": self._limit(limit),
            "_source": ["news_id", "category", "source", "title", "summary", "link", "published_at",
                        "fetched_at", "enrichment_status", "analysis"],
        }
        response = await self.client.search(index=self.index, body=body)
        hits = response["hits"]["hits"]
        total = response["hits"].get("total", 0)
        return {"total": total.get("value", 0) if isinstance(total, dict) else total,
                "items": [{**hit.get("_source", {}), "_score": hit.get("_score")} for hit in hits]}

    async def tone_summary(
        self, *, symbol: str | None, categories: list[str] | None,
        published_after: datetime | None, published_before: datetime | None,
    ) -> dict[str, Any]:
        size = self.max_results
        body = {
            "query": {"bool": {"filter": self.build_filters(
                categories=categories, symbol=symbol, published_after=published_after, published_before=published_before)}},
            "size": size,
            "sort": [{"published_at": {"order": "desc", "unmapped_type": "date"}}],
            "_source": ["analysis.overall_tone", "analysis.overall_tone_score", "analysis.company_tones", "published_at"],
        }
        response = await self.client.search(index=self.index, body=body)
        total = response["hits"].get("total", 0)
        total_value = total.get("value", 0) if isinstance(total, dict) else total
        records: list[tuple[str, float]] = []
        for hit in response["hits"]["hits"]:
            analysis = hit.get("_source", {}).get("analysis", {})
            if symbol:
                for company in analysis.get("company_tones", []):
                    if (company.get("symbol") or "").upper() == symbol.upper():
                        records.append((company.get("tone", "NEUTRAL"), float(company.get("tone_score", 0))))
            else:
                records.append((analysis.get("overall_tone", "NEUTRAL"), float(analysis.get("overall_tone_score", 0))))
        counts = Counter(tone for tone, _ in records)
        avg = sum(score for _, score in records) / len(records) if records else 0.0
        return {"matched_documents": total_value, "analyzed_documents": len(records),
                "truncated": total_value > size, "tone_counts": dict(counts), "average_confidence": round(avg, 4)}

    async def timeline(
        self, *, symbol: str | None, categories: list[str] | None, published_after: datetime | None,
        published_before: datetime | None, interval: str,
    ) -> list[dict[str, Any]]:
        body = {
            "query": {"bool": {"filter": self.build_filters(
                categories=categories, symbol=symbol, published_after=published_after, published_before=published_before)}},
            "size": 0,
            "aggs": {"timeline": {"date_histogram": {"field": "published_at", "calendar_interval": interval,
                                                       "min_doc_count": 0},
                                    "aggs": {"tones": {"terms": {"field": KEYWORD_FIELDS["tone"], "size": 3}}}}},
        }
        response = await self.client.search(index=self.index, body=body)
        return [{"period": bucket.get("key_as_string"), "count": bucket["doc_count"],
                 "tones": {item["key"]: item["doc_count"] for item in bucket["tones"]["buckets"]}}
                for bucket in response["aggregations"]["timeline"]["buckets"]]

    async def list_categories(self) -> list[dict[str, Any]]:
        response = await self.client.search(index=self.index, body={
            "size": 0, "query": {"term": {KEYWORD_FIELDS["status"]: "COMPLETED"}},
            "aggs": {"categories": {"terms": {"field": KEYWORD_FIELDS["category"], "size": 100}}},
        })
        return [{"category": item["key"], "document_count": item["doc_count"]}
                for item in response["aggregations"]["categories"]["buckets"]]

