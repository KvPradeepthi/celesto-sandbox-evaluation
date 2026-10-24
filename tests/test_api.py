import asyncio
import pytest
from httpx import ASGITransport, AsyncClient

from api.ledger import RunLedger


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "runs.db"))
    monkeypatch.setenv("SANDBOX_MODE", "mock")
    monkeypatch.setenv("MAX_CONCURRENT_RUNS", "4")
    import importlib
    import api.main
    return importlib.reload(api.main).app


@pytest.mark.asyncio
async def test_health_and_ready_endpoints(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        health_resp = await client.get("/health")
        assert health_resp.status_code == 200
        health_data = health_resp.json()
        assert health_data["status"] == "ok"
        assert health_data["service"] == "celesto-control-plane"
        assert health_data["ledger"] == "sqlite"
        assert health_data["sandbox_mode"] == "mock"
        assert health_data["ready"] is True

        ready_resp = await client.get("/ready")
        assert ready_resp.status_code == 200
        assert ready_resp.json()["ready"] is True


@pytest.mark.asyncio
async def test_health_and_run_lifecycle(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/runs", json={"command": "echo hello"})
        assert created.status_code == 202
        run_data = created.json()
        run_id = run_data["run_id"]
        assert run_data["status"] in ("queued", "running")

        result = None
        for _ in range(30):
            res = await client.get(f"/runs/{run_id}")
            assert res.status_code == 200
            result = res.json()
            if result["status"] == "succeeded":
                break
            await asyncio.sleep(0.01)

        assert result is not None
        assert result["status"] == "succeeded"
        assert result["output"] == "hello\n"
        assert result["completed_at"] is not None
        assert result["sandbox_provider"] == "mock"


@pytest.mark.asyncio
async def test_failure_policy_is_explicit(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/runs", json={"command": "false"})
        assert created.status_code == 202
        run_id = created.json()["run_id"]

        result = None
        for _ in range(30):
            res = await client.get(f"/runs/{run_id}")
            result = res.json()
            if result["status"] == "failed":
                break
            await asyncio.sleep(0.01)

        assert result is not None
        assert result["status"] == "failed"
        assert "sandbox command exited with status 1" in result["error"]
        assert result["output"] is None
        assert result["completed_at"] is not None


@pytest.mark.asyncio
async def test_timeout_policy_is_enforced(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/runs", json={"command": "sleep forever", "timeout_seconds": 1}
        )
        assert created.status_code == 202
        run_id = created.json()["run_id"]

        result = None
        for _ in range(40):
            res = await client.get(f"/runs/{run_id}")
            result = res.json()
            if result["status"] == "timed_out":
                break
            await asyncio.sleep(0.05)

        assert result is not None
        assert result["status"] == "timed_out"
        assert result["error"] == "execution exceeded timeout policy"
        assert result["completed_at"] is not None


@pytest.mark.asyncio
async def test_input_validation(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Empty string
        res = await client.post("/runs", json={"command": ""})
        assert res.status_code == 422

        # Whitespace-only string
        res = await client.post("/runs", json={"command": "   "})
        assert res.status_code == 422

        # Timeout under lower bound
        res = await client.post("/runs", json={"command": "echo 1", "timeout_seconds": 0})
        assert res.status_code == 422

        # Timeout over upper bound
        res = await client.post("/runs", json={"command": "echo 1", "timeout_seconds": 400})
        assert res.status_code == 422

        # Invalid network mode
        res = await client.post("/runs", json={"command": "echo 1", "network": "unrestricted"})
        assert res.status_code == 422


@pytest.mark.asyncio
async def test_idempotency_key_deduplication(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {"command": "echo hello", "idempotency_key": "unique-idem-key-1"}
        resp1 = await client.post("/runs", json=payload)
        assert resp1.status_code == 202
        data1 = resp1.json()

        resp2 = await client.post("/runs", json=payload)
        assert resp2.status_code in (200, 202)
        data2 = resp2.json()

        # Both calls must return the same run_id
        assert data1["run_id"] == data2["run_id"]
        assert data2["idempotency_key"] == "unique-idem-key-1"


@pytest.mark.asyncio
async def test_list_runs_and_status_filtering(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/runs", json={"command": "echo list1"})
        await client.post("/runs", json={"command": "false"})
        await asyncio.sleep(0.05)

        all_runs = await client.get("/runs?limit=10")
        assert all_runs.status_code == 200
        items = all_runs.json()
        assert len(items) >= 2

        failed_runs = await client.get("/runs?status=failed")
        assert failed_runs.status_code == 200
        assert all(r["status"] == "failed" for r in failed_runs.json())


@pytest.mark.asyncio
async def test_get_nonexistent_run_404(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/runs/non-existent-uuid-12345")
        assert res.status_code == 404
        assert res.json()["detail"] == "run not found"


@pytest.mark.asyncio
async def test_concurrency_and_terminal_states(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        requests = [
            client.post("/runs", json={"command": "echo hello"})
            for _ in range(20)
        ]
        created = await asyncio.gather(*requests)
        run_ids = [item.json()["run_id"] for item in created]

        states = []
        for _ in range(40):
            results = await asyncio.gather(
                *(client.get(f"/runs/{run_id}") for run_id in run_ids)
            )
            states = [item.json()["status"] for item in results]
            if all(state in {"succeeded", "failed", "timed_out"} for state in states):
                break
            await asyncio.sleep(0.01)

        assert len(run_ids) == 20
        assert all(state == "succeeded" for state in states)


def test_ledger_lifecycle_transition_guard(tmp_path):
    ledger = RunLedger(str(tmp_path / "guard_test.db"))
    run = ledger.create("run-1", "echo test", {"provider": "mock"})
    assert run["status"] == "queued"

    # Valid: queued -> running
    ledger.update("run-1", "running")
    # Valid: running -> succeeded
    ledger.update("run-1", "succeeded", output="done", completed=True)

    # Invalid: succeeded -> running (terminal state cannot be mutated)
    with pytest.raises(ValueError, match="invalid lifecycle transition"):
        ledger.update("run-1", "running")


def test_ledger_crash_recovery(tmp_path):
    ledger = RunLedger(str(tmp_path / "recovery_test.db"))
    ledger.create("run-orphan-1", "sleep 100", {"provider": "mock"})
    ledger.create("run-orphan-2", "sleep 200", {"provider": "mock"})
    ledger.update("run-orphan-2", "running")

    # Simulate crash recovery
    recovered = ledger.recover_pending_runs()
    assert recovered == 2

    orphan1 = ledger.get("run-orphan-1")
    orphan2 = ledger.get("run-orphan-2")
    assert orphan1["status"] == "failed"
    assert "process restarted" in orphan1["error"]
    assert orphan2["status"] == "failed"
    assert "process restarted" in orphan2["error"]
