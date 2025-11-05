from fastapi.testclient import TestClient

from app.main import app


def test_analytics_requires_c_level():
    with TestClient(app) as client:
        response = client.get("/analytics", auth=("Natasha", "hrpass123"))
        assert response.status_code == 403


def test_analytics_reports_queries():
    with TestClient(app) as client:
        chat_response = client.post(
            "/chat",
            json={"message": "Summarize the engineering master plan.", "top_k": 2},
            auth=("Tony", "password123"),
        )
        assert chat_response.status_code == 200

        analytics_response = client.get("/analytics", auth=("Priya", "cboard123"))
        assert analytics_response.status_code == 200
        payload = analytics_response.json()
        per_role = payload["queries"]["per_role"]
        assert per_role["engineering"]["total"] >= 1
        assert "cache_entries" in payload
