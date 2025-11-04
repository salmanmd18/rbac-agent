from fastapi.testclient import TestClient

from app.main import app


def test_chat_sql_path_for_hr_role():
    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "SELECT full_name, performance_rating FROM hr_hr_data LIMIT 2"},
            auth=("Natasha", "hrpass123"),
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["role"] == "hr"
        assert "Structured query result" in payload["answer"]
        assert any(ref["source"] == "data/hr/hr_data.csv" for ref in payload["references"])
