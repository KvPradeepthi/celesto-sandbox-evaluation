# Concurrency Control & High-Throughput Governance

The control plane is designed to handle bursty, high-throughput agent submissions without degrading sandbox stability or overwhelming host compute.

## 1. Concurrency Architecture

- **Process-Level Semaphore**:
  An `asyncio.Semaphore(MAX_CONCURRENT_RUNS)` governs active sandbox executions. The default limit is 4 concurrent microVM runs per container, configurable via environment variable.
- **Durable Queueing**:
  When request arrival rate exceeds available semaphore capacity, additional runs are recorded as `queued` in the SQLite ledger. As active executions complete, queued tasks immediately acquire slots and transition to `running`.
- **Database Concurrency (SQLite WAL Mode)**:
  To prevent `database is locked` errors during bursty concurrent read/write traffic:
  - SQLite is initialized with **WAL mode** (`PRAGMA journal_mode=WAL`), allowing concurrent readers to proceed without blocking writers.
  - A busy timeout of 5,000ms (`PRAGMA busy_timeout=5000`) provides resilient backoff handling for simultaneous transaction commits.

## 2. Empirical Concurrency Verification

During the automated 20-run evaluation (`scripts/run_evaluation.py`), all 20 requests were submitted simultaneously via `asyncio.gather`:
- **18 accepted runs** were queued, dispatched through the concurrency semaphore, and reached valid terminal states (`12 succeeded`, `4 failed`, `2 timed_out`).
- **2 invalid requests** were rejected at the API boundary (HTTP 422).
- Zero database locking errors or unhandled race conditions occurred.
- P50 submission latency remained under 45ms.
