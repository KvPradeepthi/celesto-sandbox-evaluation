# Problem Statement: Secure AI Agent Command Execution & Auditable Sandboxing

## 1. The Challenge of Unconstrained Agent Execution

Modern autonomous AI agents (such as coding assistants, terminal automation agents, and web-browsing agents) require arbitrary command execution to install dependencies, run test suites, execute build pipelines, and manipulate filesystems. However, allowing an agent to execute shell commands directly on a host machine introduces catastrophic security and operational risks:

1. **Host Compromise & Privilege Escalation**: Agent-generated commands can access host environment variables, cloud provider credentials (`~/.aws`, `~/.kube`, SSH keys), and sensitive files.
2. **Destructive Operations**: Accidental or hallucinated commands (e.g., `rm -rf /`, fork bombs, disk filling) can render developer workstations or shared production servers unusable.
3. **Container Breakout Risks**: Standard Linux containers share the host kernel. If misconfigured with root privileges or sensitive mounts, container escapes can compromise the entire host node.
4. **Uncontrolled Network Egress**: Malicious or hijacked agents can exfiltrate proprietary code, establish reverse shells, or participate in distributed denial-of-service attacks.
5. **Observability & Auditability Gaps**: Ephemeral script execution without a durable control plane leaves no auditable record of what commands were attempted, their exact outcomes, execution latencies, or failure causes.

---

## 2. Architectural Solution: The Celesto Control Plane

This project implements an auditable, lightweight **FastAPI Control Plane** backed by **Celesto microVM sandboxes** and a **persistent SQLite run ledger**.

### Key Architectural Pillars

- **Hardware-Isolated Sandboxing**: All user and agent-supplied commands execute behind a strict `SandboxRunner` abstraction. When configured with `SANDBOX_MODE=celesto`, execution runs inside hardware-virtualized microVMs (via Firecracker, QEMU, or Celesto Cloud Sandboxes) where guest code has zero access to the host kernel or host credentials.
- **Write-Ahead Run Ledger**: Before any command is scheduled for sandbox execution, the control plane persists a durable record (`queued` state) in SQLite with a unique UUID. Every lifecycle transition (`running`, `succeeded`, `failed`, `timed_out`, `rejected`) is permanently recorded with timestamps, stdout, and stderr.
- **Strict Network Egress Controls**: Network access is explicitly declared per request and defaults to `disabled` (`internet_settings={"mode": "off"}`). Outbound network access is never assumed to be safe.
- **Deterministic Evaluation Baseline**: A dedicated `mock` mode enables credential-free, reproducible benchmarking and integration testing without downloading gigabytes of guest OS images or requiring host virtualization privileges.
- **Idempotency & Concurrency Governance**: Concurrent requests are bounded by process-level semaphore capacity controls to prevent resource exhaustion, and optional idempotency keys guarantee that duplicate submissions do not trigger duplicate execution.
