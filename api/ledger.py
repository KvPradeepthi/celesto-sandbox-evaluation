import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunLedger:
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    command TEXT NOT NULL,
                    status TEXT NOT NULL,
                    output TEXT,
                    error TEXT,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    idempotency_key TEXT
                )
                """
            )
            # Add index for idempotency_key
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_runs_idempotency ON runs(idempotency_key)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at DESC)"
            )
            # Handle schema migration if idempotency_key column was missing
            cursor = connection.execute("PRAGMA table_info(runs)")
            columns = [row["name"] for row in cursor.fetchall()]
            if "idempotency_key" not in columns:
                connection.execute("ALTER TABLE runs ADD COLUMN idempotency_key TEXT")
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def create(
        self,
        run_id: str,
        command: str,
        metadata: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        created_at = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs(run_id, command, status, metadata, created_at, idempotency_key)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, command, "queued", json.dumps(metadata), created_at, idempotency_key),
            )
            connection.commit()
        return self.get(run_id)

    def get_by_idempotency_key(self, idempotency_key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE idempotency_key = ? ORDER BY created_at DESC LIMIT 1",
                (idempotency_key,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["metadata"] = json.loads(result["metadata"])
        return result

    def update(
        self,
        run_id: str,
        status: str,
        *,
        output: str | None = None,
        error: str | None = None,
        completed: bool = False,
    ) -> dict[str, Any]:
        current = self.get(run_id)
        allowed = {
            "queued": {"running", "rejected"},
            "running": {"succeeded", "failed", "timed_out"},
        }
        if status != current["status"] and status not in allowed.get(current["status"], set()):
            raise ValueError(f"invalid lifecycle transition: {current['status']} -> {status}")
        completed_at = utc_now() if completed else None
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE runs
                SET status = ?, output = ?, error = ?, completed_at = COALESCE(?, completed_at)
                WHERE run_id = ?
                """,
                (status, output, error, completed_at, run_id),
            )
            connection.commit()
        return self.get(run_id)

    def get(self, run_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        result = dict(row)
        result["metadata"] = json.loads(result["metadata"])
        return result

    def list(self, limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if status:
                rows = connection.execute(
                    "SELECT * FROM runs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [{**dict(row), "metadata": json.loads(row["metadata"])} for row in rows]

    def recover_pending_runs(self) -> int:
        """Mark any leftover uncompleted runs from a previous crashed process as failed."""
        now = utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE runs
                SET status = 'failed',
                    error = 'server process restarted before execution completed',
                    completed_at = ?
                WHERE status IN ('queued', 'running')
                """,
                (now,),
            )
            connection.commit()
            return cursor.rowcount
