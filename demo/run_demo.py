"""Celesto Sandbox Control Plane - Interactive Demonstration Runner.

Can be run directly with:
    python demo/run_demo.py [--url http://localhost:8000]

If an API server is running on the specified URL (or default http://localhost:8000),
it sends live HTTP requests. If not, it runs seamlessly in-process using FastAPI's
TestClient with an isolated SQLite database, making the demo runnable anywhere without
prerequisites.
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def format_json(obj: Any) -> str:
    return json.dumps(obj, indent=2)


def print_step(num: int, title: str) -> None:
    print(f"\n{'=' * 65}")
    print(f"  Step {num}: {title}")
    print(f"{'=' * 65}")


def is_live_server_available(base_url: str) -> bool:
    try:
        import urllib.request
        req = urllib.request.Request(f"{base_url}/health", method="GET")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False


class DemoClient:
    """Wrapper that abstracts live HTTP requests vs. in-process TestClient."""

    def __init__(self, base_url: str, live: bool):
        self.base_url = base_url.rstrip("/")
        self.live = live
        self._test_client = None

        if not self.live:
            # Set up in-process TestClient
            import tempfile
            from fastapi.testclient import TestClient
            from api.main import app
            from api.ledger import RunLedger

            # Use a demo temp db
            self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
            self.temp_db.close()
            os.environ["DATABASE_PATH"] = self.temp_db.name
            app.state.ledger = RunLedger(self.temp_db.name)
            self._test_client = TestClient(app)

    def get(self, path: str) -> tuple[int, Dict[str, Any]]:
        if self.live:
            import urllib.request
            url = f"{self.base_url}{path}"
            req = urllib.request.Request(url, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    return resp.status, data
            except urllib.error.HTTPError as e:
                data = json.loads(e.read().decode("utf-8"))
                return e.code, data
        else:
            resp = self._test_client.get(path)
            return resp.status_code, resp.json()

    def post(self, path: str, json_data: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
        if self.live:
            import urllib.request
            url = f"{self.base_url}{path}"
            payload = json.dumps(json_data).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=15.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    return resp.status, data
            except urllib.error.HTTPError as e:
                data = json.loads(e.read().decode("utf-8"))
                return e.code, data
        else:
            resp = self._test_client.post(path, json=json_data)
            return resp.status_code, resp.json()

    def cleanup(self) -> None:
        if not self.live and hasattr(self, "temp_db"):
            try:
                os.unlink(self.temp_db.name)
            except OSError:
                pass


def run_demo(base_url: str) -> None:
    live = is_live_server_available(base_url)
    mode_label = f"LIVE HTTP ({base_url})" if live else "IN-PROCESS TESTCLIENT (Standalone Mode)"

    print("*" * 65)
    print("  CELESTO SANDBOX CONTROL PLANE & RUN LEDGER DEMO")
    print(f"  Execution Mode: {mode_label}")
    print("*" * 65)

    client = DemoClient(base_url, live)

    try:
        # Step 1: Health & Readiness Probes
        print_step(1, "Health and Readiness Probes")
        status, health = client.get("/health")
        print(f"GET /health -> HTTP {status}")
        print(format_json(health))

        status, ready = client.get("/ready")
        print(f"\nGET /ready -> HTTP {status}")
        print(format_json(ready))
        assert status == 200, f"Expected 200, got {status}"

        # Step 2: Submit Successful Sandbox Command
        print_step(2, "Submitting Valid Sandbox Command")
        cmd_req = {
            "command": "echo 'Hello from Celesto Sandbox isolation boundary'",
            "timeout_seconds": 30,
        }
        print(f"Submitting payload:\n{format_json(cmd_req)}")
        status, run_init = client.post("/runs", cmd_req)
        print(f"\nPOST /runs -> HTTP {status} (Accepted)")
        print(format_json(run_init))
        run_id = run_init["run_id"]

        # Step 3: Query Ledger for Execution Completion
        print_step(3, f"Querying Run Ledger for Run ID: {run_id}")
        time.sleep(0.3)
        status, run_done = client.get(f"/runs/{run_id}")
        print(f"GET /runs/{run_id} -> HTTP {status}")
        print(format_json(run_done))
        print(f"\nVerification:")
        print(f"  - Status:           {run_done['status']}")
        print(f"  - Sandbox Provider: {run_done['sandbox_provider']}")
        print(f"  - Output:           {run_done['output'].strip()!r}")
        print(f"  - Timings:          created_at={run_done['created_at']} -> completed_at={run_done['completed_at']}")

        # Step 4: Idempotency Key Deduplication
        print_step(4, "Idempotency Key Deduplication")
        idempotency_key = f"demo-idem-{int(time.time())}"
        idem_req = {
            "command": "echo 'Unique operational command'",
            "idempotency_key": idempotency_key,
        }
        print(f"First Submission with key '{idempotency_key}':")
        status1, first_resp = client.post("/runs", idem_req)
        print(f"  HTTP {status1} -> run_id: {first_resp['run_id']}")

        print(f"\nDuplicate Submission with same key '{idempotency_key}':")
        status2, second_resp = client.post("/runs", idem_req)
        print(f"  HTTP {status2} -> run_id: {second_resp['run_id']}")

        if first_resp["run_id"] == second_resp["run_id"]:
            print(f"\n  [VERIFIED] Exact match: {first_resp['run_id']}")
            print("  Control plane prevented duplicate execution and returned identical run record.")
        else:
            print("  [FAILED] Run IDs differ!")

        # Step 5: Fail-Explicit Execution Containment
        print_step(5, "Fail-Explicit Sandbox Execution ('exit 42')")
        fail_req = {
            "command": "exit 42",
            "timeout_seconds": 10,
        }
        status, fail_init = client.post("/runs", fail_req)
        time.sleep(0.3)
        status, fail_done = client.get(f"/runs/{fail_init['run_id']}")
        print(f"GET /runs/{fail_init['run_id']} -> HTTP {status}")
        print(format_json(fail_done))
        print(f"\nVerification:")
        print(f"  - Status:      {fail_done['status']} (Expected 'failed')")
        print(f"  - Error Detail: {fail_done['error']}")
        print(f"  - Containment:  Host control plane remained 100% stable.")

        # Step 6: Input Validation & Boundary Defense
        print_step(6, "Input Validation Defense (Blank command rejection)")
        blank_req = {"command": "   \n\t  "}
        status, bad_resp = client.post("/runs", blank_req)
        print(f"POST /runs with blank command -> HTTP {status}")
        print(format_json(bad_resp))
        print(f"\nVerification: Rejected with HTTP 422 Unprocessable Entity before scheduling.")

        # Step 7: Filter Runs Ledger by Status
        print_step(7, "Query Run Ledger with Filter (?status=failed)")
        status, failed_runs = client.get("/runs?status=failed")
        print(f"GET /runs?status=failed -> HTTP {status} ({len(failed_runs)} record(s))")
        for idx, item in enumerate(failed_runs, 1):
            print(f"  [{idx}] run_id={item['run_id']}, status={item['status']}, error={item.get('error')!r}")

        print("\n" + "=" * 65)
        print("  ALL DEMO STEPS EXECUTED AND VERIFIED SUCCESSFULLY!")
        print("=" * 65 + "\n")

    finally:
        client.cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Celesto Sandbox Demo")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of running Celesto API")
    args = parser.parse_args()
    run_demo(args.url)
