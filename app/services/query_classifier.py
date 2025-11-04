from __future__ import annotations

import re
from enum import Enum
from typing import Iterable, Set


class QueryType(str, Enum):
    RAG = "rag"
    SQL = "sql"


class QueryClassifier:
    """Lightweight heuristic classifier to route queries to SQL or RAG pipelines."""

    SQL_KEYWORDS: Set[str] = {
        "select",
        "from",
        "where",
        "group by",
        "order by",
        "limit",
        "sum",
        "avg",
        "average",
        "count",
        "join",
        "having",
        "min",
        "max",
    }

    COMPARISON_PATTERN = re.compile(r"[<>]=?|==|!=")
    SQL_START_PATTERN = re.compile(r"^\s*(with\s+|select\s+)", re.IGNORECASE)

    def classify(self, query: str, structured_tables: Iterable[str]) -> QueryType:
        text = (query or "").strip().lower()
        if not text:
            return QueryType.RAG

        if self.SQL_START_PATTERN.match(text):
            return QueryType.SQL

        keyword_hits = sum(1 for keyword in self.SQL_KEYWORDS if keyword in text)
        has_comparison = bool(self.COMPARISON_PATTERN.search(text))
        mentions_table = any(table in text for table in structured_tables)

        if keyword_hits >= 2 and (has_comparison or mentions_table):
            return QueryType.SQL

        if mentions_table and has_comparison:
            return QueryType.SQL

        return QueryType.RAG
