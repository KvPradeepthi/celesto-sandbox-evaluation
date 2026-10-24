# Celesto Sandbox Control Plane - Demo Suite

This directory contains reproducible demo assets verifying the complete lifecycle of the Celesto Sandbox control plane and SQLite run ledger.

## Demo Options

You can experience and verify the demonstration in three ways:

### Option 1: Standalone Python Demo Runner (Recommended)
Works cross-platform on Windows, macOS, and Linux. Automatically detects if the API is listening on `http://localhost:8000` (e.g., via Docker Compose or uvicorn). If not running, it runs seamlessly in-process using FastAPI's `TestClient` with an isolated temporary SQLite ledger.

```bash
# Run against live server or standalone in-process
python demo/run_demo.py

# Or target a specific remote/custom host
python demo/run_demo.py --url http://127.0.0.1:8000
```

### Option 2: PowerShell Demo Script
Sends actual HTTP requests to the running control plane:

```powershell
# Start the stack first:
docker compose up -d

# Execute demo script:
.\demo\demo.ps1
```

### Option 3: Interactive Visual Terminal Player (`demo_recording.html`)
Open [`demo_recording.html`](demo_recording.html) directly in any web browser (Chrome, Edge, Firefox, Safari).
- Zero external dependencies or network CDNs (100% offline).
- Simulated animated terminal playback with adjustable speeds (1x, 2x, 5x, Instant).
- Scrubbable progress bar, step navigation pills, and complete transcript viewer.

### Option 4: Full HD MP4 Video Recording (`demo_recording.mp4`)
A pre-rendered 58-second 720p H.264 video recording ([`demo_recording.mp4`](demo_recording.mp4)) showcasing the entire terminal interaction, from health check to isolation and ledger verification. Can be played in VLC, Windows Media Player, QuickTime, or uploaded directly to any review portal.
- Can be re-generated deterministically anytime via: `python scripts/record_demo_video.py`

---

## What the Demo Verifies

| Step | Scenario | Expected Behavior | Verification |
|---|---|---|---|
| **1. Probes** | `GET /health`, `GET /ready` | HTTP 200 `{"status": "ok", "ready": true}` | Verified service readiness & DB connection |
| **2. Submission** | `POST /runs` (`echo ...`) | HTTP 202 Accepted, status `queued` | Assigned UUID, recorded in ledger |
| **3. Lifecycle** | `GET /runs/{run_id}` | State transitions `queued` -> `running` -> `succeeded` | Timings recorded, output captured |
| **4. Idempotency** | Duplicate `idempotency_key` | Identical `run_id` returned without re-execution | Deduped at control plane boundary |
| **5. Fail-Explicit** | `POST /runs` (`exit 42`) | Status `failed`, non-zero status captured in error | Host control plane remains 100% stable |
| **6. Validation** | `POST /runs` (`"   "`) | HTTP 422 Unprocessable Entity | Rejected before task scheduling |
| **7. Ledger Query** | `GET /runs?status=failed` | Filtered array of matching runs | Filtered without database table locking |

---

## Security & Reproducibility Notice
- All mock and evaluated commands run without requiring cloud credentials or proprietary sandbox keys.
- User commands are executed inside Celesto sandbox boundaries (Firecracker microVM / QEMU / cloud).
- No host commands are executed directly on the host shell.
- Zero secrets or API keys are stored in the repository.
