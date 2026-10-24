import json
import os
import sqlite3
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.ledger import RunLedger


def main() -> None:
    seed_path = Path(__file__).resolve().parents[1] / "seeds" / "runs.json"
    ledger = RunLedger(os.getenv("DATABASE_PATH", "data/runs.db"))
    seeds = json.loads(seed_path.read_text(encoding="utf-8"))
    loaded = 0
    for index, item in enumerate(seeds):
        run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"celesto-seed:{index}"))
        try:
            ledger.create(run_id, item["command"], {
                "provider": "seed",
                "network": "disabled",
                "expected_status": item["expected_status"],
            })
        except sqlite3.IntegrityError:
            continue
        loaded += 1
    print(f"loaded {loaded} new seed rows")


if __name__ == "__main__":
    main()
