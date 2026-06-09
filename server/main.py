import os
import json
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict
import uuid

from fastapi import FastAPI, Query, HTTPException

from nats_observe.config import NATSotelSettings
from nats_observe.client import Client as NATSotel

from nats.aio.msg import Msg
from opentelemetry.trace import SpanKind

from openapi_schema_validator import validate
from jsonschema.exceptions import ValidationError

from models import AgentHeartbeat, AgentInfo

# ======== CONFIG ============
NATS_URL = ["nats://192.168.19.157:4222"]
OUTPUT_SUBJECT = "agent.*.out"
HEARTBEAT_SUBJECT = "agent.heartbeat_module"
HEARTBEAT_INTERVAL = 5                      # Agents send heartbeat every 5s
HEARTBEAT_TIMEOUT = HEARTBEAT_INTERVAL * 2  # If no heartbeat in 10s => dead
# ============================

# In-memory cache
measurement_cache: Dict[str, Any] = {} # TODO: Replace with DBOS
agent_cache: Dict[str, AgentInfo] = {}
settings = NATSotelSettings(service_name="server", servers=NATS_URL)
nc: NATSotel = NATSotel(settings, kind=SpanKind.SERVER)

# NATS connection & subscription
async def nats_connect():
    await nc.connect(settings.servers, name="server", verbose=True, reconnect_time_wait=0)
    print(f"[Cache] Connected to NATS: {NATS_URL}")

    async def heartbeat_handler(msg: Msg):
        try:
            data = json.loads(msg.data.decode())
            hb = AgentHeartbeat(agent_id=data["agent"]["id"], hostname=data["agent"]["hostname"])

            existing = agent_cache.get(hb.agent_id)
            now = datetime.now(timezone.utc)

            if existing:
                existing.last_seen = hb.timestamp
                existing.alive = True
                existing.config = data
                existing.total_heartbeats += 1
            else:
                agent_cache[hb.agent_id] = AgentInfo(
                    agent_id=hb.agent_id,
                    alive=True,
                    hostname=hb.hostname,
                    last_seen=hb.timestamp,
                    config=data,
                    first_seen=now,
                    total_heartbeats=1
                )
            print(f"[Cache] Updated heartbeat: {hb.agent_id} @ {hb.timestamp}")

        except Exception as e:
            print("[Cache] Error parsing heartbeat:", e)

    await nc.subscribe(HEARTBEAT_SUBJECT, cb=heartbeat_handler)

# Background cleanup task (mark dead)
async def cleanup_agents():
    while True:
        now = datetime.now(timezone.utc)
        for agent_id, info in agent_cache.items():
            if (now - info.last_seen) > timedelta(seconds=HEARTBEAT_TIMEOUT):
                if info.alive:
                    info.alive = False
                    print(f"[Cache] Agent {agent_id} marked DEAD (last seen {info.last_seen})")
        await asyncio.sleep(HEARTBEAT_INTERVAL)

async def lifespan(app: FastAPI):
    # Startup code can be placed here if needed
    asyncio.create_task(nats_connect())
    asyncio.create_task(cleanup_agents())

    yield

    # Shutdown code can be placed here if needed 

app = FastAPI(title="Agent Server", version="1.0", lifespan=lifespan)


# ======================
#       API ROUTES
# ======================

@app.get("/")
async def root():
    return {
        "status": "ok",
        "total_agents": len(agent_cache),
        "alive_agents": len([a for a in agent_cache.values() if a.alive]),
    }


@app.get("/agents", response_model=Dict[str, AgentInfo])
async def get_all_agents():
    """
    Get all agents (alive and dead) with metadata.
    """
    return agent_cache


@app.get("/agents/alive", response_model=Dict[str, AgentInfo])
async def get_alive_agents():
    """
    Get only currently alive agents.
    """
    return {aid: info for aid, info in agent_cache.items() if info.alive}


@app.get("/agents/dead", response_model=Dict[str, AgentInfo])
async def get_dead_agents():
    """
    Get only agents considered dead (missed heartbeat).
    """
    return {aid: info for aid, info in agent_cache.items() if not info.alive}


@app.get("/agents/{agent_id}", response_model=AgentInfo)
async def get_agent(agent_id: str):
    """
    Get detailed info about a specific agent.
    """
    agent = agent_cache.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@app.post("/agent/{agent_id}/{module_name}", )
async def run_module(
        agent_id: str, 
        module_name: str, 
        module_request: Dict[str, Any], 
        # Query parameter with default and alias 
        untracked: bool = Query(False) 
    ):
    try:
        agent = agent_cache.get(agent_id)
        
        if not agent or not agent.alive:
            return {"error": "Agent is not alive"}
        
        if not untracked:
            if "id" not in module_request:
                module_request["id"] = str(uuid.uuid4())
        
        # Validation
        all_spec = agent.config["agent"]["modules"]["spec"]
    
        if module_name in all_spec:
            try:
                validate(module_request, all_spec[module_name]['input_schema'])
            except ValidationError as ex:
                return {"error": "Validation Error", "message": ex.message}
            except Exception as ex:
                return {"error": "Unknown Error", "message": ex.message}

            await nc.publish(all_spec[module_name]['input_subject'], json.dumps(module_request).encode())

        if module_request.get("id", None):
            measurement_cache[module_request["id"]] = None

        return {
            "message": "success",
            "id": module_request.get("id", None)
        }
    except Exception as ex:
        return {"error": "..."}

