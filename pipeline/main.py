import asyncio
import enum
import json
import uuid
from typing import Any, Dict
from datetime import datetime

from nats import NATS
from nats.aio.msg import Msg

from fastapi import FastAPI, Query, HTTPException
from sqlmodel import Field, Session, SQLModel, create_engine, select

# In-memory cache
measurement_cache: Dict[str, Any] = {}
OUTPUT_SUBJECT = "agent.*.out"
engine = create_engine("sqlite:///database.db")
nc : NATS = NATS()

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

async def runs_monitor():
    async def monitor_handler(msg: Msg):
        # print(f"[Run Monitor] Running : {msg.data.decode()}")

        try:
            data = json.loads(msg.data.decode())
            measurement_query_id = data.get("query.id")
            if measurement_query_id:
                measurement_state = MeasurementState(
                    query_id=uuid.UUID(data.get("query.id")), 
                    query_type=data.get("query.name"), 
                    query_agent=data.get("query.agent"), 
                    status=Status(data.get("status", "running"))
                )
                with Session(engine) as session:
                    session.add(measurement_state)
                    print(f"[Run Monitor] Updated measurement state: {measurement_state}")
                    session.commit()
        except Exception as e:
            print("[Run Monitor] Error parsing run update:", e)

    await nc.subscribe(OUTPUT_SUBJECT, cb=monitor_handler)


async def lifespan(app: FastAPI):
    # Startup code can be placed here if needed 
    SQLModel.metadata.create_all(engine)
    await nc.connect("nats://localhost:4222")
    asyncio.create_task(runs_monitor())

    yield

app = FastAPI(title="Pipeline Server", version="1.0", lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "ok", "message": "Welcome to the Pipeline Server!"}

@app.get("/runs/status/{measurement_id}")
async def get_run_status(measurement_id: uuid.UUID):
    """
    Get the status of a specific run by its ID.
    """

    measurement_history = []
    with Session(engine) as session:
        statement = select(MeasurementState).where(MeasurementState.query_id == measurement_id) \
            .order_by(MeasurementState.created_at.desc())
        
        with Session(engine) as session:
            for history in session.exec(statement):
                measurement_history.append({
                    "status": history.status.value,
                    "timestamp": history.created_at.isoformat()
                })
            current_state = session.exec(statement).first()
    return {
        "measurement_id": measurement_id,
        "status": current_state.status if current_state else None,
        "history": measurement_history if current_state else []
    }