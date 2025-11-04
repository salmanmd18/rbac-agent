from pathlib import Path

import pytest

from app.services.sql_service import SQLExecutionError, SQLService


DATA_ROOT = Path(__file__).resolve().parent.parent / "resources" / "data"


@pytest.fixture(scope="module")
def sql_service() -> SQLService:
    return SQLService(data_root=DATA_ROOT)


def test_available_tables_filters_by_department(sql_service: SQLService):
    tables = sql_service.available_tables(["hr"])
    assert "hr_hr_data" in tables
    assert all(metadata.department == "hr" for metadata in tables.values())


def test_execute_select_allowed(sql_service: SQLService):
    rows, columns, metadata = sql_service.execute(
        "SELECT full_name, performance_rating FROM hr_hr_data LIMIT 3",
        departments=["hr"],
    )
    assert "full_name" in columns
    assert len(rows) <= 3
    assert metadata[0].table_name == "hr_hr_data"


def test_execute_blocks_unauthorized_access(sql_service: SQLService):
    with pytest.raises(SQLExecutionError):
        sql_service.execute(
            "SELECT * FROM hr_hr_data",
            departments=["finance"],  # no HR access
        )


def test_execute_rejects_non_select(sql_service: SQLService):
    with pytest.raises(SQLExecutionError):
        sql_service.execute(
            "DROP TABLE hr_hr_data",
            departments=["hr"],
        )
