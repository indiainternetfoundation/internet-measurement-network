from datetime import datetime
import enum
import uuid

from sqlmodel import Field, SQLModel


class Status(enum.Enum):
    STARTED = "started"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class MeasurementState(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True, )
    created_at: datetime = Field(default_factory=lambda: datetime.now())
    query_id: uuid.UUID
    query_type: str
    query_agent: str
    status: Status
