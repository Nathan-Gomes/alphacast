import time

from alphacast import runs
from alphacast.config import ResearchConfig
from alphacast.runs import DEFAULT_RUN_ID, RunRegistry, RunRequest


def _wait(registry: RunRegistry, run_id: str, timeout: float = 60) -> runs.RunRecord:
    deadline = time.time() + timeout
    while time.time() < deadline:
        record = registry.get(run_id)
        if record.status in {"complete", "failed"}:
            return record
        time.sleep(0.1)
    raise AssertionError("run did not finish")


def test_a_failing_study_is_recorded_with_its_reason(monkeypatch):
    def broken(request):
        raise ValueError("Yahoo Finance returned prices for 3 of 12 tickers")

    monkeypatch.setattr(runs, "load_prices", broken)
    registry = RunRegistry()
    record = registry.submit(RunRequest("yahoo", ["A"] * 12, "custom", ResearchConfig(models=("momentum",)), "x"))
    finished = _wait(registry, record.id)
    assert finished.status == "failed"
    assert "3 of 12" in finished.error
    assert finished.workspace is None


def test_eviction_never_removes_the_default_workspace(monkeypatch):
    monkeypatch.setattr(runs, "MAX_RUNS", 2)
    monkeypatch.setattr(runs, "MAX_ACTIVE_RUNS", 10)
    registry = RunRegistry()
    request = RunRequest("synthetic", [], "us_large_cap", ResearchConfig(models=("momentum",)), "s")
    ids = []
    for _ in range(3):
        ids.append(registry.submit(request).id)
        _wait(registry, ids[-1])
    listed = {row["id"] for row in registry.list()}
    assert DEFAULT_RUN_ID in listed
    assert ids[-1] in listed and ids[0] not in listed
