# Control Plane Capabilities

The Celesto Sandbox Control Plane exposes an auditable, high-performance REST API for executing agent commands inside isolated sandboxes while maintaining an immutable run ledger.

## 1. API Endpoints

| Method | Path | Status Code | Purpose |
|---|---|---|---|
| `GET` | `/health` | `200` / `503` | Liveness probe verifying control plane and SQLite ledger readiness |
| `GET` | `/ready` | `200` / `503` | Readiness probe confirming the service is ready to accept incoming runs |
| `POST` | `/runs` | `202` / `422` | Submit command for asynchronous sandboxed execution |
| `GET` | `/runs/{run_id}` | `200` / `404` | Retrieve detailed run metadata, status, output, and timestamps |
| `GET` | `/runs` | `200` | List newest-first runs with pagination (`limit`) and `status` filtering |

## 2. Request & Execution Specifications

- **Command Limits**: Commands must be non-empty strings between 1 and 4,000 characters. Whitespace-only commands are rejected at the API boundary with HTTP 422.
- **Timeouts**: Configurable per-request between 1 and 300 seconds (default: 30 seconds). Enforced via `asyncio.wait_for`.
- **Network Controls**: Declared per-request as `disabled` (default) or `restricted`. `restricted` requires an explicit egress destination allowlist.
- **Idempotency**: Clients can supply an optional `idempotency_key` (up to 128 characters). Re-submitting the same key returns the existing run without re-executing.
- **Concurrency Governance**: An asynchronous semaphore enforces `MAX_CONCURRENT_RUNS` (default: 4 active runs). Excess work remains queued in SQLite.

## 3. Sandboxing Backends

1. **Mock Backend (`SANDBOX_MODE=mock`)**:
   - Deterministic execution engine for CI/CD and local evaluation.
   - Evaluates commands in memory; never spawns host processes, shell interpreters, or external subVMs.
   - Produces deterministic outputs (`echo hello` -> `hello\n`, `false` -> exit 1, `sleep forever` -> timeout).
2. **Celesto MicroVM Backend (`SANDBOX_MODE=celesto`)**:
   - Uses the official `celesto` Python SDK.
   - **Local MicroVM (`CELESTO_BACKEND=firecracker` or `qemu`)**: Boots hardware-virtualized guests using KVM/Firecracker or QEMU with vsock control channels and outbound network disabled (`internet_settings={"mode": "off"}`).
   - **Cloud Sandbox (`CELESTO_BACKEND=cloud`)**: Connects to the hosted Celesto Cloud API using `CELESTO_API_KEY`.
