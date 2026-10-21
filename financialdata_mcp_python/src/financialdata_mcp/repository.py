from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable

from pymongo import DESCENDING, MongoClient
from pymongo.database import Database

from .serialization import json_safe

VALID_SOURCES = {"SCREENER", "NSE_XBRL"}
VALID_SCOPES = {"STANDALONE", "CONSOLIDATED"}


class FinancialRepository:
    def __init__(self, database: Database[Any], max_results: int = 500) -> None:
        self.db = database
        self.max_results = max_results

    @classmethod
    def connect(cls, uri: str, database: str, max_results: int = 500) -> "FinancialRepository":
        client: MongoClient[Any] = MongoClient(uri, appname="financialdata-mcp", serverSelectionTimeoutMS=5000)
        return cls(client[database], max_results)

    def ping(self) -> None:
        self.db.command("ping")

    def _limit(self, value: int) -> int:
        if value < 1:
            raise ValueError("limit must be positive")
        return min(value, self.max_results)

    @staticmethod
    def _head_collection(source: str) -> str:
        if source == "SCREENER":
            return "screener_snapshots"
        if source == "NSE_XBRL":
            return "financial_filings"
        raise ValueError(f"Unsupported source: {source}")

    def _dataset_ids(self, symbol: str, sources: Iterable[str], scope: str) -> list[str]:
        ids: list[str] = []
        for source in sources:
            head = self.db[self._head_collection(source)].find_one(
                {"kind": "head", "symbol": symbol, "source": source, "scope": scope},
                {"dataset_id": 1},
            )
            if head and head.get("dataset_id"):
                ids.append(head["dataset_id"])
        return ids

    def get_current_facts(
        self,
        *,
        symbol: str,
        source: str,
        scope: str,
        statement: str | None = None,
        metrics: list[str] | None = None,
        period_type: str | None = None,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        dataset_ids = self._dataset_ids(symbol, [source], scope)
        if not dataset_ids:
            return []
        query: dict[str, Any] = {
            "dataset_id": {"$in": dataset_ids},
            "symbol": symbol,
            "source": source,
            "scope": scope,
            "validation_status": "VALID",
        }
        if statement:
            query["statement"] = statement
        if metrics:
            query["metric"] = {"$in": metrics}
        if period_type:
            query["period_type"] = period_type
        if period_start or period_end:
            date_filter: dict[str, datetime] = {}
            if period_start:
                date_filter["$gte"] = period_start
            if period_end:
                date_filter["$lte"] = period_end
            query["period_end"] = date_filter
        projection = {
            "_id": 0,
            "dataset_id": 1,
            "symbol": 1,
            "source": 1,
            "scope": 1,
            "statement": 1,
            "metric": 1,
            "metric_label": 1,
            "value": 1,
            "unit": 1,
            "period_kind": 1,
            "period_type": 1,
            "period_start": 1,
            "period_end": 1,
            "duration_months": 1,
            "dimensions": 1,
            "source_document_id": 1,
            "observed_at": 1,
        }
        cursor = self.db.financial_facts.find(query, projection).sort(
            [("period_end", DESCENDING), ("statement", 1), ("metric", 1)]
        ).limit(self._limit(limit))
        return json_safe(list(cursor))

    def get_statement(
        self,
        *,
        symbol: str,
        scope: str,
        statement: str,
        period_type: str | None,
        periods: int,
    ) -> list[dict[str, Any]]:
        facts = self.get_current_facts(
            symbol=symbol,
            source="SCREENER",
            scope=scope,
            statement=statement,
            period_type=period_type,
            limit=self.max_results,
        )
        rows: dict[tuple[str, str], dict[str, Any]] = {}
        for fact in facts:
            key = (fact.get("period_end") or "", fact.get("period_type") or "")
            row = rows.setdefault(key, {"period_end": key[0], "period_type": key[1], "metrics": {}})
            row["metrics"][fact["metric"]] = {
                "label": fact.get("metric_label"), "value": fact.get("value"), "unit": fact.get("unit")
            }
        return sorted(rows.values(), key=lambda row: row["period_end"], reverse=True)[: self._limit(periods)]

    def compare_sources(
        self,
        *,
        symbol: str,
        scope: str,
        metrics: list[str] | None,
        period_end: datetime | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        ids = self._dataset_ids(symbol, sorted(VALID_SOURCES), scope)
        if not ids:
            return []
        query: dict[str, Any] = {
            "dataset_id": {"$in": ids}, "symbol": symbol, "scope": scope, "validation_status": "VALID",
            "$or": [{"dimensions": {}}, {"dimensions": {"$exists": False}}],
        }
        if metrics:
            query["metric"] = {"$in": metrics}
        if period_end:
            query["period_end"] = period_end
        cursor = self.db.financial_facts.find(query, {"_id": 0}).sort("period_end", DESCENDING).limit(
            self._limit(limit) * 2
        )
        groups: dict[tuple[Any, ...], dict[str, Any]] = {}
        for fact in cursor:
            key = (fact.get("statement"), fact.get("metric"), fact.get("period_type"), fact.get("period_end"), fact.get("unit"))
            group = groups.setdefault(key, {
                "statement": key[0], "metric": key[1], "period_type": key[2],
                "period_end": json_safe(key[3]), "unit": key[4], "sources": {},
            })
            group["sources"][fact["source"]] = json_safe(fact.get("value"))
        result = []
        for group in groups.values():
            values = group["sources"]
            group["comparison_status"] = "BOTH" if len(values) == 2 else "SINGLE_SOURCE"
            result.append(group)
        return result[: self._limit(limit)]

    def list_metrics(self, *, symbol: str, source: str, scope: str) -> list[dict[str, Any]]:
        ids = self._dataset_ids(symbol, [source], scope)
        if not ids:
            return []
        pipeline = [
            {"$match": {"dataset_id": {"$in": ids}, "validation_status": "VALID"}},
            {"$group": {"_id": {"statement": "$statement", "metric": "$metric"},
                         "label": {"$first": "$metric_label"}, "units": {"$addToSet": "$unit"}}},
            {"$sort": {"_id.statement": 1, "_id.metric": 1}},
            {"$limit": self.max_results},
        ]
        return [{"statement": row["_id"]["statement"], "metric": row["_id"]["metric"],
                 "label": row.get("label"), "units": row.get("units", [])}
                for row in self.db.financial_facts.aggregate(pipeline)]

    def get_ingestion_status(self, *, symbol: str | None, limit: int) -> list[dict[str, Any]]:
        query = {"symbol": symbol} if symbol else {}
        cursor = self.db.ingestion_runs.find(query, {"_id": 0}).sort("started_at", DESCENDING).limit(self._limit(limit))
        return json_safe(list(cursor))

