import os
import asyncio
import uuid, json
from typing import Any, Dict
from datetime import datetime, timedelta, timezone

from nats.aio.msg import Msg
from fastapi import APIRouter, Query, HTTPException

from openapi_schema_validator import validate
from jsonschema.exceptions import ValidationError

from ..core.connections import nc
from .models.agent import AgentHeartbeat, AgentInfo

OUTPUT_SUBJECT = "agent.*.out"
HEARTBEAT_SUBJECT = "agent.heartbeat_module"
HEARTBEAT_INTERVAL = 5                      # Agents send heartbeat every 5s
HEARTBEAT_TIMEOUT = HEARTBEAT_INTERVAL * 2  # If no heartbeat in 10s => dead

# In-memory cache
measurement_cache: Dict[str, Any] = {}
agent_cache: Dict[str, AgentInfo] = {}

# NATS connection & subscription
async def nats_connect(nc):
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

# Create a router instead of a FastAPI instance
router = APIRouter(prefix="/agents", tags=["agents"])

@router.get("/", response_model=Dict[str, AgentInfo])
async def get_all_agents():
    """
    Get all agents (alive and dead) with metadata.
    """
    return agent_cache


@router.get("/alive", response_model=Dict[str, AgentInfo])
async def get_alive_agents():
    """
    Get only currently alive agents.
    """
    return {aid: info for aid, info in agent_cache.items() if info.alive}


@router.get("/dead", response_model=Dict[str, AgentInfo])
async def get_dead_agents():
    """
    Get only agents considered dead (missed heartbeat).
    """
    return {aid: info for aid, info in agent_cache.items() if not info.alive}


@router.get("/{agent_id}", response_model=AgentInfo)
async def get_agent(agent_id: str):
    """
    Get detailed info about a specific agent.
    """
    agent = agent_cache.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/{agent_id}/{module_name}", )
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
        return {"error": "...", "message": str(ex)}

