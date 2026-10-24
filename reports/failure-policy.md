# Failure Policy & Error Sanitization

The control plane adheres to a strict, fail-explicit policy. It guarantees that failures are never silently swallowed, retried invisibly, or disguised as successes.

## 1. Core Principles

1. **Zero Success-Shaped Fallbacks**:
   If a command exits with code 1, it will never report status `succeeded` or return an empty error. If an SDK is missing, misconfigured, or unreachable, execution immediately transitions to `failed`.
2. **Deterministic Status Mapping**:
   - Schema violations (e.g. empty or whitespace command) ➔ HTTP 422 `rejected` before ledger entry.
   - Non-zero command exit codes ➔ Terminal `failed` with exit code and truncated error log.
   - Command timeouts ➔ Terminal `timed_out` with `error="execution exceeded timeout policy"`.
   - Host/Server abrupt shutdown ➔ Terminal `failed` with `error="server process restarted before execution completed"`.
3. **Error Sanitization**:
   Internal host exceptions, file system paths, and raw tracebacks are intercepted and sanitized before recording in the public ledger. Clients receive concise diagnostic messages rather than leaking internal host details.
4. **Immediate Ledger Synchronization**:
   Terminal states and completion timestamps are committed to SQLite *before* worker tasks release the concurrency semaphore. This prevents race conditions where polling clients see stale `running` states after execution finishes.
