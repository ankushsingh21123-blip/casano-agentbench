"""API endpoint coverage via TestClient: happy paths + validation errors."""

import pytest


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_tasks(client):
    resp = client.get("/tasks")
    assert resp.status_code == 200
    tasks = resp.json()
    assert len(tasks) == 5
    ids = {t["id"] for t in tasks}
    assert ids == {
        "arithmetic-01",
        "json-extraction-01",
        "instruction-following-01",
        "tool-use-01",
        "summary-01",
    }
    for task in tasks:
        assert set(task) == {"id", "name", "category", "description", "prompt"}


def test_agents_reports_bifrost_not_configured_by_default(client):
    resp = client.get("/agents")
    assert resp.status_code == 200
    body = resp.json()
    assert body["bifrost_configured"] is False
    names = [a["name"] for a in body["agents"]]
    assert names == ["echo", "rule", "bifrost"]


def test_agents_never_exposes_keys(client, monkeypatch):
    monkeypatch.setenv("BIFROST_API_KEY", "SECRET_VALUE_XYZ_123")
    monkeypatch.setenv("BIFROST_BASE_URL", "http://localhost:8080")
    resp = client.get("/agents")
    assert resp.status_code == 200
    assert resp.json()["bifrost_configured"] is True
    assert "SECRET_VALUE_XYZ_123" not in resp.text


def test_create_run_echo_all_tasks_score_zero(client):
    resp = client.post("/runs", json={"agent": "echo"})
    assert resp.status_code == 201
    run = resp.json()
    assert run["agent"] == "echo"
    assert len(run["results"]) == 5
    assert all(r["score"] == 0.0 for r in run["results"])
    for r in run["results"]:
        assert r["details"]
        assert r["error"] is None


def test_create_run_rule_all_tasks_score_perfect(client):
    resp = client.post("/runs", json={"agent": "rule"})
    assert resp.status_code == 201
    run = resp.json()
    assert all(r["score"] == 1.0 for r in run["results"])


def test_create_run_task_subset(client):
    resp = client.post("/runs", json={"agent": "rule", "task_ids": ["arithmetic-01", "summary-01"]})
    assert resp.status_code == 201
    assert [r["task_id"] for r in resp.json()["results"]] == ["arithmetic-01", "summary-01"]


def test_create_run_unknown_agent_rejected(client):
    resp = client.post("/runs", json={"agent": "mallory"})
    assert resp.status_code == 422


def test_create_run_unknown_task_rejected(client):
    resp = client.post("/runs", json={"agent": "rule", "task_ids": ["nope-01"]})
    assert resp.status_code == 422


def test_create_run_empty_task_list_rejected(client):
    resp = client.post("/runs", json={"agent": "rule", "task_ids": []})
    assert resp.status_code == 422


def test_create_run_too_many_task_ids_rejected(client):
    resp = client.post("/runs", json={"agent": "rule", "task_ids": ["arithmetic-01"] * 21})
    assert resp.status_code == 422


def test_create_run_agent_name_too_long_rejected(client):
    resp = client.post("/runs", json={"agent": "x" * 33})
    assert resp.status_code == 422


def test_create_run_missing_agent_rejected(client):
    resp = client.post("/runs", json={})
    assert resp.status_code == 422


def test_list_runs_and_get_run_detail(client):
    assert client.get("/runs").json() == []
    created = client.post("/runs", json={"agent": "rule", "task_ids": ["arithmetic-01"]}).json()
    runs = client.get("/runs").json()
    assert len(runs) == 1
    assert runs[0]["id"] == created["id"]
    assert runs[0]["task_count"] == 1
    assert runs[0]["avg_score"] == 1.0
    detail = client.get(f"/runs/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == created["id"]
    assert detail.json()["results"][0]["output"] == "156"


def test_get_run_not_found(client):
    assert client.get("/runs/does-not-exist").status_code == 404


def test_leaderboard_empty_when_no_runs(client):
    assert client.get("/leaderboard").json() == []


def test_leaderboard_aggregates_only_from_stored_runs(client):
    client.post("/runs", json={"agent": "echo"})
    client.post("/runs", json={"agent": "rule"})
    board = client.get("/leaderboard").json()
    assert len(board) == 2
    assert board[0]["agent"] == "rule"
    assert board[0]["avg_score"] == 1.0
    assert board[0]["runs"] == 1
    assert board[0]["tasks"] == 5
    assert board[1]["agent"] == "echo"
    assert board[1]["avg_score"] == 0.0
