from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime, timezone


class AgentHeartbeat(BaseModel):
    agent_id: str
    hostname: str
    timestamp: datetime = Field(default_factory=lambda : datetime.now(timezone.utc))


class AgentInfo(BaseModel):
    agent_id: str
    alive: bool
    hostname: str
    last_seen: datetime
    config: Dict[str, Any] = Field(default_factory=dict)
    first_seen: datetime
    total_heartbeats: int
