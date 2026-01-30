"""
Module execution router - handles module execution endpoints
"""
from fastapi import APIRouter, Query
from typing import Dict, Any

from main import execute_module_workflow, execution_queue

router = APIRouter(prefix="/agent", tags=["modules"])


@router.post("/{agent_id}/{module_name}")
async def execute_module(
    agent_id: str,
    module_name: str,
    module_request: Dict[str, Any],
    untracked: bool = Query(False)
) -> Dict[str, Any]:
    """Execute module synchronously via durable workflow"""
    result = await execute_module_workflow(
        agent_id,
        module_name,
        module_request,
        untracked
    )
    return result


@router.post("/{agent_id}/{module_name}/async")
async def execute_module_async(
    agent_id: str,
    module_name: str,
    module_request: Dict[str, Any]
) -> Dict[str, Any]:
    """Enqueue module execution for async processing"""
    handle = execution_queue.enqueue(
        execute_module_workflow,
        agent_id,
        module_name,
        module_request,
        False
    )
    
    return {
        "status": "enqueued",
        "workflow_id": handle.workflow_id
    }