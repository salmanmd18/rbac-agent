from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import duckdb


class SQLExecutionError(Exception):
    """Raised when a structured query cannot be executed safely."""


@dataclass(frozen=True)
class TableMetadata:
    department: str
    table_name: str
    path: Path
    columns: Tuple[str, ...]


class SQLService:
    """Executes whitelisted SQL queries over department-scoped CSV data."""

    SAFE_QUERY_PATTERN = re.compile(r"^\s*select\s", re.IGNORECASE)
    TABLE_PATTERN = re.compile(r"\b(from|join)\s+([a-zA-Z_][\w]*)", re.IGNORECASE)

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self._tables = self._discover_tables()

    @staticmethod
    def _sanitize_identifier(*parts: str) -> str:
        raw = "_".join(parts)
        safe = re.sub(r"[^a-zA-Z0-9_]", "_", raw)
        return re.sub(r"_+", "_", safe).strip("_").lower()

    def _discover_tables(self) -> Dict[str, TableMetadata]:
        tables: Dict[str, TableMetadata] = {}
        if not self.data_root.exists():
            return tables

        for department_dir in self.data_root.iterdir():
            if not department_dir.is_dir():
                continue
            department = department_dir.name.lower()
            for csv_path in department_dir.glob("*.csv"):
                table_name = self._sanitize_identifier(department, csv_path.stem)
                columns = self._read_header(csv_path)
                tables[table_name] = TableMetadata(
                    department=department,
                    table_name=table_name,
                    path=csv_path,
                    columns=tuple(columns),
                )
        return tables

    @staticmethod
    def _read_header(path: Path) -> Sequence[str]:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
        return [column.strip() for column in header if column]

    def available_tables(self, departments: Iterable[str]) -> Dict[str, TableMetadata]:
        normalized = {dept.strip().lower() for dept in departments if dept}
        return {
            name: metadata
            for name, metadata in self._tables.items()
            if metadata.department in normalized
        }

    def execute(self, query: str, departments: Iterable[str]) -> Tuple[List[Dict[str, str]], List[str], List[TableMetadata]]:
        query = (query or "").strip()
        if not query:
            raise SQLExecutionError("Query is empty.")
        if ";" in query:
            raise SQLExecutionError("Multiple statements are not supported.")
        if not self.SAFE_QUERY_PATTERN.match(query):
            raise SQLExecutionError("Only SELECT queries are supported.")

        allowed_tables = self.available_tables(departments)
        if not allowed_tables:
            raise SQLExecutionError("No structured data is available for this role.")

        referenced = self._extract_tables(query)
        if not referenced:
            raise SQLExecutionError("Query must reference at least one known table.")

        invalid = [table for table in referenced if table not in allowed_tables]
        if invalid:
            raise SQLExecutionError(
                f"Query references unauthorized tables: {', '.join(sorted(invalid))}."
            )

        safe_query = query if " limit " in query.lower() else f"{query.rstrip()} LIMIT 50"

        with duckdb.connect(database=":memory:") as connection:
            for table_name, metadata in allowed_tables.items():
                connection.execute(
                    f"CREATE OR REPLACE VIEW {table_name} AS "
                    f"SELECT * FROM read_csv_auto('{metadata.path.as_posix()}', HEADER=TRUE);"
                )
            try:
                result = connection.execute(safe_query)
            except duckdb.Error as exc:
                raise SQLExecutionError(f"Query execution failed: {exc}") from exc

            columns = [col[0] for col in result.description]
            rows = [dict(zip(columns, map(self._stringify, row))) for row in result.fetchall()]

        return rows, columns, [allowed_tables[name] for name in referenced]

    @classmethod
    def _extract_tables(cls, query: str) -> List[str]:
        tables: List[str] = []
        for match in cls.TABLE_PATTERN.findall(query):
            tables.append(match[1].lower())
        # Ensure deterministic order
        unique_tables = []
        for table in tables:
            if table not in unique_tables:
                unique_tables.append(table)
        return unique_tables

    @staticmethod
    def _stringify(value) -> str:
        if value is None:
            return "NULL"
        return str(value)


def to_markdown_table(rows: List[Dict[str, str]], columns: Sequence[str], max_rows: int = 10) -> str:
    if not rows:
        return "No rows returned for this query."
    display_rows = rows[:max_rows]
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in display_rows:
        body.append("| " + " | ".join(row.get(column, "") for column in columns) + " |")
    footer = ""
    if len(rows) > max_rows:
        footer = f"\n_{len(rows) - max_rows} more rows not shown (limited to {max_rows})._"
    return "\n".join([header, separator, *body]) + footer
