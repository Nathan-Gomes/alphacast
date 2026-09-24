import time

from fastapi.testclient import TestClient

from alphacast.app import app

client = TestClient(app)


def wait_for(run_id: str, timeout: float = 120) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        record = client.get(f"/api/runs/{run_id}").json()
        if record["status"] in {"complete", "failed"}:
            return record
        time.sleep(0.2)
    raise AssertionError("run did not finish")


def test_health_reports_the_default_workspace():
    body = client.get("/api/health").json()
    assert body["service"] == "alphacast"
    assert body["default_workspace"] is True


def test_catalog_lists_models_with_estimates_and_defaults():
    catalog = client.get("/api/catalog").json()
    models = {model["id"]: model for model in catalog["models"]}
    assert set(models) == {"momentum", "ridge", "elastic_net", "random_forest", "gradient_boosting", "ensemble"}
    assert models["momentum"]["default"] and not models["random_forest"]["default"]
    assert all(model["seconds"] > 0 for key, model in models.items() if key != "ensemble")
    assert models["ensemble"]["seconds"] == 0  # derived from the others, nothing to fit
    assert {universe["id"] for universe in catalog["universes"]} == {"us_large_cap", "starter_30"}


def test_default_workspace_serves_live_rankings_and_security_detail():
    workspace = client.get("/api/runs/default").json()["workspace"]
    assert workspace["signal_date"] > workspace["last_rebalance"]
    ticker = workspace["live"][0]["ticker"]
    detail = client.get(f"/api/runs/default/securities/{ticker.lower()}").json()
    assert detail["ticker"] == ticker
    assert detail["prices"]["dates"] and detail["history"] and detail["attribution"]


def test_a_submitted_run_completes_and_exports():
    created = client.post("/api/runs", json={"source": "synthetic", "models": ["momentum", "ridge"]})
    assert created.status_code == 202
    record = wait_for(created.json()["id"])
    assert record["status"] == "complete", record["error"]
    assert record["headline"]["model"] in {"momentum", "ridge"}
    assert {row["model"] for row in record["workspace"]["summaries"]} == {"momentum", "ridge"}
    export = client.get(f"/api/runs/{record['id']}/export")
    assert export.status_code == 200
    assert "attachment" in export.headers["content-disposition"]


def test_invalid_requests_are_rejected_with_a_reason():
    assert client.post("/api/runs", json={"models": []}).status_code == 422
    assert client.post("/api/runs", json={"models": ["xgboost"]}).status_code == 422
    lonely = client.post("/api/runs", json={"models": ["momentum", "ridge", "ensemble"]})
    assert lonely.status_code == 422 and "ensemble" in lonely.json()["detail"]
    too_few = client.post("/api/runs", json={"source": "yahoo", "universe": "custom", "tickers": ["AAPL"]})
    assert too_few.status_code == 422 and "ten" in too_few.json()["detail"]
    small_buffer = client.post("/api/runs", json={"top_n": 15, "hold_buffer": 10})
    assert small_buffer.status_code == 422 and "buffer" in small_buffer.json()["detail"]
    backwards = client.post("/api/runs", json={"start": "2025-01-01", "end": "2020-01-01"})
    assert backwards.status_code == 422


def test_unknown_runs_and_tickers_return_404():
    assert client.get("/api/runs/missing").status_code == 404
    assert client.get("/api/runs/default/securities/NOPE").status_code == 404
