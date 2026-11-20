from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ScheduleCreate(BaseModel):
    cron_expression: str = Field(
        ...,
        json_schema_extra={"example": "*/5 * * * *"},
    )
    max_runs: int | None = Field(
        None,
        ge=1,
        description="Maximum number of times to run. null = unlimited"
    )

class ScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    cron_expression: str
    next_run_at: datetime | None
    status: str
    max_runs: int | None
    run_count: int
