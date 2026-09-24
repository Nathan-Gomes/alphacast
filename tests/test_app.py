from fastapi.testclient import TestClient

from alphacast.app import app


def test_health_describes_the_research_service():
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json()["service"] == "alphacast"


def test_synthetic_endpoint_returns_declared_run_artifacts():
    response = TestClient(app).post(
        "/api/research",
        json={"source": "synthetic", "models": ["momentum"], "top_n": 5},
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["quality"]["source"] == "synthetic"
    assert payload["summaries"][0]["model"] == "momentum"
    assert payload["periods"]
    assert payload["latest_rankings"]
    assert payload["monitoring"]
    assert payload["regimes"]
