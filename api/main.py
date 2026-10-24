import asyncio
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, status

from .ledger import RunLedger
from .models import HealthResponse, RunRequest, RunResponse
from .sandbox import SandboxError, create_runner


DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/runs.db")
SANDBOX_MODE = os.getenv("SANDBOX_MODE", "mock")
MAX_CONCURRENT_RUNS = int(os.getenv("MAX_CONCURRENT_RUNS", "4"))
ledger = RunLedger(DATABASE_PATH)
runner = create_runner(SANDBOX_MODE)
semaphore = asyncio.Semaphore(MAX_CONCURRENT_RUNS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Recover any uncompleted runs from prior crashed instances
    recovered = ledger.recover_pending_runs()
    if recovered:
        import logging
        logging.getLogger("celesto").info("Recovered %d pending runs on startup", recovered)
    yield


app = FastAPI(
    title="Celesto Sandbox Control Plane",
    description="Run-ledger API and evaluation control plane for Celesto sandboxes",
    version="1.0.0",
    lifespan=lifespan,
)


def format_response(run: dict) -> RunResponse:
    return RunResponse(
        run_id=run["run_id"],
        status=run["status"],
        command=run["command"],
        output=run.get("output"),
        error=run.get("error"),
        created_at=run["created_at"],
        completed_at=run.get("completed_at"),
        sandbox_provider=run["metadata"].get("provider", SANDBOX_MODE),
        idempotency_key=run.get("idempotency_key"),
    )


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    if not ledger.ready():
        raise HTTPException(status_code=503, detail="ledger unavailable")
    return HealthResponse(
        status="ok",
        service="celesto-control-plane",
        ledger="sqlite",
        sandbox_mode=SANDBOX_MODE,
        ready=True,
    )


@app.get("/ready", response_model=HealthResponse)
async def ready() -> HealthResponse:
    if not ledger.ready():
        raise HTTPException(status_code=503, detail="ledger not ready")
    return HealthResponse(
        status="ok",
        service="celesto-control-plane",
        ledger="sqlite",
        sandbox_mode=SANDBOX_MODE,
        ready=True,
    )


@app.post("/runs", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_run(request: RunRequest) -> RunResponse:
    # Check idempotency if key provided
    if request.idempotency_key:
        existing = ledger.get_by_idempotency_key(request.idempotency_key)
        if existing:
            return format_response(existing)

    run_id = str(uuid.uuid4())
    metadata = {
        "provider": SANDBOX_MODE,
        "network": request.network,
        "timeout_seconds": request.timeout_seconds,
    }
    run = ledger.create(
        run_id=run_id,
        command=request.command,
        metadata=metadata,
        idempotency_key=request.idempotency_key,
    )
    asyncio.create_task(execute_run(run_id, request))
    return format_response(run)


async def execute_run(run_id: str, request: RunRequest) -> None:
    async with semaphore:
        ledger.update(run_id, "running")
        try:
            result = await asyncio.wait_for(
                runner.run(request.command, request.timeout_seconds, request.network),
                timeout=request.timeout_seconds,
            )
        except asyncio.TimeoutError:
            ledger.update(
                run_id,
                "timed_out",
                error="execution exceeded timeout policy",
                completed=True,
            )
        except SandboxError as exc:
            ledger.update(run_id, "failed", error=str(exc), completed=True)
        except asyncio.CancelledError:
            ledger.update(run_id, "failed", error="execution cancelled", completed=True)
            raise
        except Exception as exc:
            del exc
            ledger.update(
                run_id,
                "failed",
                error="unexpected sandbox failure",
                completed=True,
            )
        else:
            ledger.update(run_id, "succeeded", output=result.output, completed=True)


@app.get("/runs", response_model=list[RunResponse])
async def list_runs(
    limit: int = Query(default=50, ge=1, le=100),
    status: str | None = Query(default=None),
) -> list[RunResponse]:
    return [format_response(run) for run in ledger.list(limit=limit, status=status)]


@app.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str) -> RunResponse:
    try:
        return format_response(ledger.get(run_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
