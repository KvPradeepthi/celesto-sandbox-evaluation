# Execution Lifecycle & State Machine

The control plane implements a strict, unidirectional state machine governing all run attempts.

```
       [Client Request]
              │
      Validation Failed? ──► [HTTP 422 Rejected] (No ledger row)
              │ Validation Passed
              ▼
          [queued] ◄────────────── Persisted to SQLite with UUIDv4
              │
     Semaphore Acquired
              │
              ▼
          [running]
              │
       ───────┼───────────────
      │       │               │
      ▼       ▼               ▼
 [succeeded] [failed]    [timed_out]   (Terminal States)
```

## 1. Lifecycle State Definitions

1. **`rejected`**: The request violated schema constraints (empty command, whitespace-only, timeout out of bounds, invalid network type). Rejected at the FastAPI boundary with HTTP 422 without writing to the ledger.
2. **`queued`**: A unique UUIDv4 run identifier is generated and a durable row is inserted into SQLite with status `queued` and ISO 8601 `created_at` timestamp before execution is scheduled.
3. **`running`**: The background worker acquires a slot in the concurrency semaphore and updates the ledger row status to `running`.
4. **`succeeded`**: The command completed with exit status 0. The output is captured, status is set to `succeeded`, and `completed_at` timestamp is recorded.
5. **`failed`**: The command completed with a non-zero exit code or the sandbox encountered a runtime error. Stderr or error description is recorded in `error`.
6. **`timed_out`**: Command execution exceeded the configured `timeout_seconds`. The runner is cancelled, status is set to `timed_out`, and `error="execution exceeded timeout policy"` is recorded.

## 2. Transition Guardrails & Invariants

- **Terminal Immutability**: States `succeeded`, `failed`, and `timed_out` are strictly terminal. The transition guard in `api/ledger.py` raises `ValueError` if any code attempts to mutate a terminal run.
- **Allowed Transitions**:
  - `queued` ➔ `running`
  - `running` ➔ `succeeded` | `failed` | `timed_out`
- **Crash Recovery**: When the FastAPI service boots, `ledger.recover_pending_runs()` detects any orphan rows left in `queued` or `running` state from an abrupt host shutdown and marks them as `failed` with `error="server process restarted before execution completed"`.
- **Idempotency**: Submissions containing an `idempotency_key` return the existing run record if the key was already registered, preventing duplicate execution attempts.
