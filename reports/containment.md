# Security Containment & Isolation Boundary

The Celesto Sandbox Control Plane enforces an explicit security perimeter between untrusted agent-generated commands and the host environment.

## 1. The Isolation Architecture

All command execution is decoupled behind the `SandboxRunner` abstract interface:

```
[Agent Request] ──► [FastAPI Control Plane] ──► [Run Ledger]
                                 │
                                 ▼
                     [SandboxRunner Interface]
                                 │
             ┌───────────────────┴───────────────────┐
             ▼                                       ▼
  [MockCelestoRunner]                       [CelestoRunner]
  • In-memory execution                     • Hardware-isolated microVM
  • Zero host subprocesses                  • Firecracker / KVM / vsock
  • Safe for CI and testing                 • Cloud Sandboxes
```

### Key Security Guarantees:

1. **No Host Shell Invocation**:
   Neither the mock runner nor the production adapter executes `os.system()`, `subprocess.Popen(..., shell=True)`, or host command interpreters.
2. **MicroVM Boundary**:
   Under `SANDBOX_MODE=celesto`, execution occurs inside a dedicated guest microVM with separate kernel memory, guest init system, and virtualized hardware. A kernel panic or privilege escalation inside the guest cannot escape to the host node.
3. **Egress Network Containment**:
   Network access defaults to `disabled` (`internet_settings={"mode": "off"}`). Agent commands cannot open external sockets, connect to command-and-control servers, or exfiltrate environment variables. `restricted` mode requires an explicitly configured host allowlist.
4. **Credential Isolation**:
   No host credentials (`~/.aws`, `~/.ssh`, cloud tokens, or host environment variables) are passed to the guest. The run ledger persists only command strings, outputs, errors, and metadata.
5. **Non-Root Container Hardening**:
   The API Dockerfile creates and runs as `appuser` (UID 10001), adhering to the principle of least privilege.
