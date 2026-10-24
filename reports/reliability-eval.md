# Reliability evaluation

The executable evaluation is `python scripts/run_evaluation.py`. It covers 12 successes,
4 deterministic command failures, 2 timeouts, and 2 invalid requests, with concurrent
submission and ledger reads. It writes raw measurements to
`reports/reliability-results.json`; that file is generated from the latest local mock
run, not hand-authored.

The latest generated result (`2026-10-24T08:14:43Z`) is:

| Metric | Result |
|---|---:|
| total attempted | 20 |
| accepted for execution | 18 |
| succeeded | 12 |
| sandbox failures | 4 |
| timed out | 2 |
| rejected requests | 2 |
| unexpected errors | 0 |
| submission latency p50 | 40.91 ms |
| submission latency p95 | 65.26 ms |
| maximum submission latency | 67.24 ms |

The complete machine-readable result is in
[`reliability-results.json`](reliability-results.json).
