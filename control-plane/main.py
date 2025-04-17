from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import dataclasses
import asyncio
import json
import nats
import datetime
import time
import enum
import os
import uuid

# from .nats_monitor.client import AccountMonitorClient, ServerMonitorClient, SystemMonitorClient
from .nats_monitor.connz import ConnzCollector
from .nats_monitor.healthz import HealthzCollector

nats_connection = None
connected_agents = {}  # Store information about connected clients (via heartbeat)

NATS_URL = os.environ.get("NATS_URL", "nats://localhost:4222")
NATS_MON = os.environ.get("NATS_MON", "http://localhost:8222")
AGENT_TIMEOUT = datetime.timedelta(seconds=15)



class AgentStatus(enum.StrEnum):
    Active = "Active"
    Inactive = "Inactive"

class AgentMessage(BaseModel):
    reply_to: str
    request_id: uuid.UUID | str | None
    message: str

class PublishPayload(BaseModel):
    subject: str
    data: AgentMessage

@asynccontextmanager
async def lifespan(app: FastAPI):
    global nats_connection
    account = "YOUR_ACCOUNT"  # Replace with your custom NATS account name
    try:
        nats_connection = await nats.connect(NATS_URL, name="control-plane") # account=account
        print(f"FastAPI server connected to NATS at {NATS_URL} with account '{account}'")
        asyncio.create_task(monitor_heartbeats())
        asyncio.create_task(cleanup_inactive_agents())
    except Exception as e:
        print(f"Error connecting to NATS: {e}")

    yield

    if nats_connection and not nats_connection.is_closed:
        await nats_connection.close()
        print("FastAPI server disconnected from NATS.")

async def cleanup_inactive_agents():
    """Periodically removes agents that haven't sent a heartbeat recently."""
    while True:
        await asyncio.sleep(5)  # Check for inactive agents every 5 seconds
        current_time = datetime.datetime.utcnow()
        inactive_agents = [
            client_id
            for client_id, agent_info in connected_agents.items()
            if current_time - agent_info["last_seen"] > AGENT_TIMEOUT
        ]
        for client_id in inactive_agents:
            # del connected_agents[client_id]
            connected_agents[client_id] = {"last_seen": connected_agents[client_id].get("last_seen"), "status": AgentStatus.Inactive}
            print(f"Agent '{client_id}' removed due to inactivity.")

app = FastAPI(lifespan=lifespan)

async def monitor_heartbeats():
    """Monitors heartbeat messages from agents."""
    heartbeat_subject = "agents.heartbeat"
    async def heartbeat_handler(msg):
        try:
            data = json.loads(msg.data.decode())
            client_id = data.get("id")
            if client_id:
                connected_agents[client_id] = {**data, "last_seen": datetime.datetime.utcnow(), "status": AgentStatus.Active}
        except Exception as e:
            print(f"Error processing heartbeat: {e}")

    if nats_connection:
        await nats_connection.subscribe(heartbeat_subject, cb=heartbeat_handler)
        print(f"FastAPI server subscribed to '{heartbeat_subject}' for agent monitoring.")

async def get_nats_server_stats():
    """Retrieves basic stats from the NATS server."""
    if nats_connection:
        try:
            stats = nats_connection.stats
            return stats
        except Exception as e:
            print(f"Error fetching NATS server stats: {e}")
            return None
    return None

async def get_nats_account_info(account_name="YOUR_ACCOUNT"): # Replace with the account to inspect
    """Retrieves information about a specific NATS account."""
    if nats_connection:
        try:
            account_info = await nats_connection.account_info(account_name)
            return account_info
        except Exception as e:
            print(f"Error fetching NATS account info for '{account_name}': {e}")
            return None
    return None

@app.post("/publish/")
async def publish_endpoint(payload: PublishPayload):
    """Publishes data to a specified NATS subject."""
    if nats_connection and not nats_connection.is_closed:
        try:
            await nats_connection.publish(payload.subject, payload.data.json().encode())
            return {"message": f"Published to '{payload.subject}'"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error publishing to NATS: {e}")
    else:
        raise HTTPException(status_code=503, detail="Not connected to NATS server.")

@app.get("/nats/stats/")
async def get_nats_stats():
    """Returns NATS server statistics."""
    stats = await get_nats_server_stats()
    if stats:
        return stats
    else:
        raise HTTPException(status_code=500, detail="Could not retrieve NATS server stats.")

@app.get("/nats/accounts/{account_name}")
async def get_account_info(account_name: str):
    """Returns information about a specific NATS account."""
    info = await get_nats_account_info(account_name)
    if info:
        return info
    else:
        raise HTTPException(status_code=404, detail=f"Account '{account_name}' not found or could not retrieve info.")

@app.get("/agents/")
async def get_connected_agents():
    """Returns a list of currently connected agents (based on heartbeats)."""
    return connected_agents

@app.get("/connections/")
async def get_connections():
    connz = ConnzCollector([NATS_MON]).fetch()
    return {"connection": [dataclasses.asdict(con) for con in connz]}

@app.get("/health/")
async def get_health():
    connz = HealthzCollector([NATS_MON]).fetch()
    return {"connection": [dataclasses.asdict(con) for con in connz]}