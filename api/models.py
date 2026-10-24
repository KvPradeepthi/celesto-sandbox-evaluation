from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


RunStatus = Literal["queued", "running", "succeeded", "failed", "timed_out", "rejected"]


class RunRequest(BaseModel):
    command: str = Field(min_length=1, max_length=4000)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    network: Literal["disabled", "restricted"] = "disabled"
    idempotency_key: str | None = Field(default=None, max_length=128)

    @field_validator("command")
    @classmethod
    def validate_command_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("command cannot be empty or whitespace only")
        return value


class RunResponse(BaseModel):
    run_id: str
    status: RunStatus
    command: str
    output: str | None = None
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    sandbox_provider: str
    idempotency_key: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    ledger: str
    sandbox_mode: str
    ready: bool = True
