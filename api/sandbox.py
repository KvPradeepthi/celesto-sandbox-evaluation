import asyncio
import os
from dataclasses import dataclass


class SandboxError(RuntimeError):
    """A sandbox rejected or could not complete a command."""


@dataclass(frozen=True)
class ExecutionResult:
    output: str
    provider: str


class SandboxRunner:
    async def run(self, command: str, timeout_seconds: int, network: str) -> ExecutionResult:
        raise NotImplementedError


class MockCelestoRunner(SandboxRunner):
    """Deterministic runner used for local evaluation; it never executes host commands."""

    async def run(self, command: str, timeout_seconds: int, network: str) -> ExecutionResult:
        await asyncio.sleep(0)
        cmd = command.strip()
        if cmd == "echo hello":
            return ExecutionResult("hello\n", "celesto-mock")
        if cmd == "true":
            return ExecutionResult("", "celesto-mock")
        if cmd == "false":
            raise SandboxError("sandbox command exited with status 1")
        if cmd == "sleep forever":
            await asyncio.sleep(timeout_seconds + 1)
            return ExecutionResult("", "celesto-mock")
        if cmd.startswith("exit "):
            code = cmd.split()[1]
            if code != "0":
                raise SandboxError(f"sandbox command exited with status {code}")
            return ExecutionResult("", "celesto-mock")
        return ExecutionResult(f"mock execution: {command}\n", "celesto-mock")


class CelestoRunner(SandboxRunner):
    """Adapter boundary for the verified Celesto Python SDK."""

    async def run(self, command: str, timeout_seconds: int, network: str) -> ExecutionResult:
        if network == "restricted":
            raise SandboxError("restricted network mode requires a deployment-specific allowlist")

        try:
            from celesto import Computer  # type: ignore[import-not-found]
        except ImportError as exc:
            raise SandboxError(
                "Celesto SDK is not installed; use SANDBOX_MODE=mock for local evaluation"
            ) from exc

        backend = os.getenv("CELESTO_BACKEND", "firecracker").lower()

        def execute() -> ExecutionResult:
            try:
                if backend == "cloud":
                    api_key = os.getenv("CELESTO_API_KEY")
                    if not api_key:
                        raise SandboxError(
                            "CELESTO_API_KEY environment variable is required for CELESTO_BACKEND=cloud"
                        )
                    with Computer(provider="cloud", api_key=api_key) as computer:
                        result = computer.run(command, timeout=timeout_seconds)
                else:
                    with Computer(
                        local=True,
                        backend=backend,
                        comm_channel="vsock",
                        internet_settings={"mode": "off"},
                    ) as computer:
                        result = computer.run(command, timeout=timeout_seconds)
            except SandboxError:
                raise
            except Exception as exc:
                raise SandboxError(f"Celesto sandbox execution failed: {exc}") from exc

            exit_code = getattr(result, "exit_code", 0)
            output = getattr(result, "stdout", "") or ""
            error = getattr(result, "stderr", "") or ""
            if exit_code != 0:
                raise SandboxError(f"sandbox command exited with status {exit_code}: {error[:500]}")
            return ExecutionResult(output, f"celesto-{backend}")

        return await asyncio.to_thread(execute)


def create_runner(mode: str) -> SandboxRunner:
    if mode == "mock":
        return MockCelestoRunner()
    if mode == "celesto":
        return CelestoRunner()
    raise ValueError(f"unsupported SANDBOX_MODE: {mode!r}")
