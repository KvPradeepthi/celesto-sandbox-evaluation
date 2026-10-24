import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["SANDBOX_MODE"] = "mock"
os.environ["DATABASE_PATH"] = str(Path("data/evaluation.db"))
from api.main import app


async def main() -> None:
    transport = httpx.ASGITransport(app=app)
    latencies: list[float] = []
    counts = {"attempted": 0, "accepted": 0, "succeeded": 0, "failed": 0,
              "timed_out": 0, "rejected": 0, "unexpected_errors": 0}
    async with httpx.AsyncClient(transport=transport, base_url="http://evaluation") as client:
        requests = ([{"command": "echo hello"}] * 12
                    + [{"command": "false"}] * 4
                    + [{"command": "sleep forever", "timeout_seconds": 1}] * 2
                    + [{"command": ""}] * 2)
        counts["attempted"] = len(requests)
        async def submit(payload: dict) -> str | None:
            started = time.perf_counter()
            result = await client.post("/runs", json=payload)
            latencies.append((time.perf_counter() - started) * 1000)
            if result.status_code == 422:
                counts["rejected"] += 1
                return None
            if result.status_code != 202:
                counts["unexpected_errors"] += 1
                return None
            counts["accepted"] += 1
            return result.json()["run_id"]
        run_ids = [run_id for run_id in await asyncio.gather(*(submit(item) for item in requests))
                   if run_id]
        async def poll(run_id: str) -> str:
            for _ in range(100):
                result = await client.get(f"/runs/{run_id}")
                if result.status_code != 200:
                    return "unexpected_errors"
                status = result.json()["status"]
                if status in {"succeeded", "failed", "timed_out"}:
                    return status
                await asyncio.sleep(0.01)
            return "unexpected_errors"
        for status in await asyncio.gather(*(poll(run_id) for run_id in run_ids)):
            if status in counts:
                counts[status] += 1
            else:
                counts["unexpected_errors"] += 1
    result = {
        **counts,
        "latency_ms": {
            "p50": round(statistics.median(latencies), 2),
            "p95": round(sorted(latencies)[max(0, int(len(latencies) * .95) - 1)], 2),
            "max": round(max(latencies), 2),
        },
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    output = Path("reports/reliability-results.json")
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
