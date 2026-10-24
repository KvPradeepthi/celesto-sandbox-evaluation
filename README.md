# Celesto Sandbox Control Plane & Reliability Evaluation

An auditable, high-performance control plane for executing untrusted AI agent commands inside isolated sandboxes while maintaining an immutable, durable run ledger.

Designed to start with `docker compose up --build` with zero secrets required.

---

## 1. Problem Statement

Autonomous AI agents (coding assistants, terminal agents, browser harnesses) frequently generate and execute arbitrary shell commands to install dependencies, run tests, and manipulate files. Running untrusted code directly on host systems introduces severe security hazards:
- **Host Compromise**: Accidental or malicious exfiltration of host credentials (`~/.aws`, `~/.ssh`, environment variables).
- **Destructive Failures**: Unconstrained commands (fork bombs, disk exhaustion, recursive deletions) impacting shared infrastructure.
- **Auditability Gaps**: Ephemeral script execution lacking durable tracing, structured exit code tracking, or timeout enforcement.

This control plane decouples command dispatching from execution by placing all runs behind an immutable run ledger and Celesto hardware-virtualized microVM sandboxes.

Detailed analysis: [reports/problem.md](reports/problem.md).

---

## 2. Celesto Sandboxing & Usage

All execution is managed through the `SandboxRunner` adapter boundary (`api/sandbox.py`). Tool execution never invokes host shells or unrestricted subprocesses.

### Supported Sandbox Modes:
1. **Mock Backend (`SANDBOX_MODE=mock`) [Default]**:
   - In-memory deterministic execution engine for automated testing and CI.
   - Evaluates commands safely without host execution.
   - Simulates exit codes, standard outputs, and timeouts deterministically.
2. **Celesto MicroVM (`SANDBOX_MODE=celesto`, `CELESTO_BACKEND=firecracker` | `qemu`)**:
   - Boots isolated hardware-virtualized guest microVMs using the official `celesto` Python SDK.
   - Operates over vsock control channels with network egress completely disabled (`internet_settings={"mode": "off"}`).
3. **Celesto Cloud Sandbox (`SANDBOX_MODE=celesto`, `CELESTO_BACKEND=cloud`)**:
   - Creates on-demand disposable cloud computers using `CELESTO_API_KEY`.

---

## 3. Reliability Evaluation & Measured Numbers

The repository includes a reproducible, automated 20-run evaluation script (`scripts/run_evaluation.py`) testing concurrent submission, success, deterministic failure, timeouts, and validation:

| Metric | Measured Evaluation Result |
|---|---:|
| **Total Attempted** | **20** |
| **Accepted for Execution** | **18** |
| **Succeeded** | **12** |
| **Sandbox Command Failures** | **4** |
| **Timed Out** | **2** |
| **Rejected at API Boundary** | **2** |
| **Unexpected Errors** | **0** |
| **Submission Latency (p50)** | **9.52 ms** |
| **Submission Latency (p95)** | **14.67 ms** |
| **Maximum Submission Latency** | **18.51 ms** |

Raw evaluation measurements are recorded in [reports/reliability-results.json](reports/reliability-results.json).  
Detailed report: [reports/reliability-eval.md](reports/reliability-eval.md).

---

## 4. Security Containment & Failure Policy

- **Containment Boundary**: No agent commands ever execute via `os.system` or host shells. Egress networking defaults to `disabled`. The API container runs as non-root `appuser` (UID 10001). See [reports/containment.md](reports/containment.md).
- **Failure Policy**: Strict, fail-explicit design. Failures are never silently swallowed or disguised as successes. Non-zero exit codes transition to `failed` with captured error output; timeouts transition to `timed_out`. Internal host exceptions are sanitized. See [reports/failure-policy.md](reports/failure-policy.md).
- **Concurrency & Ledger Durability**: SQLite is configured with Write-Ahead Logging (`PRAGMA journal_mode=WAL`) and a 5,000ms busy timeout to prevent database locks under load. Active sandboxes are throttled via an asynchronous semaphore (`MAX_CONCURRENT_RUNS`). See [reports/concurrency.md](reports/concurrency.md).

---

## 5. Setup & Quick Start

### Option A: Run via Docker Compose (Recommended)

```powershell
Copy-Item .env.example .env
docker compose up --build
```

The container starts with non-root privileges and health checks verifying `GET /health` on port 8000.

### Option B: Local Python Development

```powershell
# Run the FastAPI control plane directly
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### Submit & Inspect Runs

```powershell
# 1. Health & readiness check
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready

# 2. Submit a sandboxed run (returns HTTP 202 Accepted)
$run = Invoke-RestMethod -Method Post http://localhost:8000/runs `
  -ContentType "application/json" -Body '{"command":"echo hello"}'

# 3. Poll run outcome
Invoke-RestMethod "http://localhost:8000/runs/$($run.run_id)"

# 4. Inspect complete run ledger
Invoke-RestMethod http://localhost:8000/runs?limit=10
```

---

## 6. Verification & Automated Testing

Run the automated test suite (11 unit and integration tests):
```powershell
python -m pytest -v
```

Execute the 20-run reliability evaluation:
```powershell
python scripts/run_evaluation.py
```

Load idempotent seed runs into the ledger:
```powershell
python scripts/load_seeds.py
```

---

## 7. Demo Walkthrough & Assets

An end-to-end demo script is provided in `demo/`:
- `demo/demo.ps1`: Interactive PowerShell demo script verifying health, run submission, execution, failure, and ledger querying.
- `demo/run_demo.py`: Python CLI demo runner testing the complete workflow and printing formatted results.
- `demo/demo_recording.html`: Visual standalone HTML5 replay of the control plane execution trace and API transactions.

See [demo/README.md](demo/README.md) for full instructions.

---

## 8. Reports & Submission Artifacts Index

- [reports/problem.md](reports/problem.md) — Security analysis of agent execution & control plane architecture
- [reports/capabilities.md](reports/capabilities.md) — Full API specification, endpoints, parameters, and backends
- [reports/lifecycle.md](reports/lifecycle.md) — State machine transitions, invariants, and crash recovery
- [reports/reliability-eval.md](reports/reliability-eval.md) — 20-run evaluation breakdown and latency metrics
- [reports/reliability-results.json](reports/reliability-results.json) — Raw machine-readable benchmark outputs
- [reports/containment.md](reports/containment.md) — Security containment, isolation boundary, and network policy
- [reports/failure-policy.md](reports/failure-policy.md) — Fail-explicit principles, error sanitization, and status mapping
- [reports/concurrency.md](reports/concurrency.md) — Semaphore capacity governance and SQLite WAL concurrency
- [seeds/runs.json](seeds/runs.json) — Sample seed runs for ledger initialization
