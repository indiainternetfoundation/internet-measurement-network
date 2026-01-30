"""
Agents router - handles agent-related endpoints
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any

from main import agent_cache

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/")
async def list_all_agents() -> Dict[str, Any]:
    """Get all agents (alive and dead)"""
    return agent_cache.agents


@router.get("/alive")
async def list_alive_agents() -> Dict[str, Any]:
    """Get only alive agents"""
    return agent_cache.get_alive()


@router.get("/dead")
async def list_dead_agents() -> Dict[str, Any]:
    """Get only dead agents"""
    return agent_cache.get_dead()


@router.get("/{agent_id}")
async def get_agent_info(agent_id: str) -> Any:
    """Get detailed info about specific agent"""
    agent = agent_cache.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent