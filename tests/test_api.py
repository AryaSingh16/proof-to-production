from fastapi.testclient import TestClient

from app.main import create_app
from app.storage import MemoryStore


def test_healthz_and_readyz():
    app = create_app(MemoryStore())
    client = TestClient(app)

    res_healthz = client.get("/healthz")
    assert res_healthz.status_code == 200
    assert res_healthz.json() == {"status": "ok"}

    res_readyz = client.get("/readyz")
    assert res_readyz.status_code == 200
    assert res_readyz.json() == {"status": "ready"}


def test_tasks_crud_flow():
    app = create_app(MemoryStore())
    client = TestClient(app)

    # Initial list is empty
    res = client.get("/tasks")
    assert res.status_code == 200
    assert res.json() == []

    # Create task
    res = client.post("/tasks", json={"title": "Test task"})
    assert res.status_code == 201
    task = res.json()
    assert task["id"] == 1
    assert task["title"] == "Test task"
    assert task["done"] is False
    assert "created_at" in task

    # List tasks
    res = client.get("/tasks")
    assert res.status_code == 200
    tasks = res.json()
    assert len(tasks) == 1
    assert tasks[0]["id"] == 1

    # Get task
    res = client.get("/tasks/1")
    assert res.status_code == 200
    assert res.json()["title"] == "Test task"

    # Delete task
    res = client.delete("/tasks/1")
    assert res.status_code == 204

    # Get task after delete returns 404
    res = client.get("/tasks/1")
    assert res.status_code == 404


def test_unknown_id_404():
    app = create_app(MemoryStore())
    client = TestClient(app)

    res = client.get("/tasks/99999")
    assert res.status_code == 404

    res = client.delete("/tasks/99999")
    assert res.status_code == 404


def test_empty_title_422():
    app = create_app(MemoryStore())
    client = TestClient(app)

    res = client.post("/tasks", json={"title": ""})
    assert res.status_code == 422


def test_metrics_route_template_label():
    app = create_app(MemoryStore())
    client = TestClient(app)

    # Create a task and GET it to trigger metric recording
    create_res = client.post("/tasks", json={"title": "Metrics test"})
    assert create_res.status_code == 201
    task_id = create_res.json()["id"]

    get_res = client.get(f"/tasks/{task_id}")
    assert get_res.status_code == 200

    # Scrape /metrics
    metrics_res = client.get("/metrics")
    assert metrics_res.status_code == 200
    content = metrics_res.text
    assert "http_requests_total" in content
    assert 'path="/tasks/{task_id}"' in content


def test_fault_injection(monkeypatch):
    monkeypatch.setenv("ENABLE_FAULT_INJECTION", "false")
    app_off = create_app(MemoryStore())
    client_off = TestClient(app_off)
    res_off = client_off.get("/debug/error")
    assert res_off.status_code == 404

    monkeypatch.setenv("ENABLE_FAULT_INJECTION", "true")
    app_on = create_app(MemoryStore())
    client_on = TestClient(app_on)
    res_on = client_on.get("/debug/error")
    assert res_on.status_code == 500

    res_slow = client_on.get("/debug/slow?ms=10")
    assert res_slow.status_code == 200
    assert res_slow.json() == {"status": "slow", "slept_ms": 10}
