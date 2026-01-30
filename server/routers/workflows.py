"""
Workflows router - handles workflow management endpoints
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional

from main import workflow_state, DBOS

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("/")
async def list_workflows(
    status: Optional[str] = None,
    limit: int = Query(100, le=1000)
) -> Dict[str, Any]:
    """
    List workflows with optional status filter.
    Status must be one of: RUNNING, COMPLETED, FAILED
    """
    if status and status not in ["RUNNING", "COMPLETED", "FAILED"]:
        raise HTTPException(
            status_code=400, 
            detail="Status must be RUNNING, COMPLETED, or FAILED"
        )
    
    workflows = []
    
    # Get workflows from our cache
    workflow_items = list(workflow_state.workflows.items())
    if len(workflow_items) > limit:
        workflow_items = workflow_items[-limit:]
    
    for workflow_id, workflow_data in workflow_items:
        current_state = workflow_state.get_current_state(workflow_id)
        
        # Apply status filter
        if status and current_state != status:
            continue
        
        state_history = workflow_state.state_history.get(workflow_id, [])
        
        workflows.append({
            "workflow_id": workflow_id,
            "agent_id": workflow_data.get("agent_id"),
            "module_name": workflow_data.get("module_name"),
            "current_state": current_state,
            "created_at": workflow_data.get("created_at"),
            "state_transitions": len(state_history)
        })
    
    # Also try to get DBOS workflows
    dbos_workflows = []
    try:
        dbos_wf_list = DBOS.list_workflows(limit=limit)
        if status:
            dbos_wf_list = [w for w in dbos_wf_list if w.status == status]
        
        dbos_workflows = [
            {
                "workflow_id": w.workflow_id,
                "status": w.status,
                "workflow_name": getattr(w, 'workflow_name', 'unknown'),
                "started_at": getattr(w, 'started_at', None)
            }
            for w in dbos_wf_list
        ]
    except Exception as e:
        print(f"[Workflows] Error listing DBOS workflows: {e}")
    
    return {
        "workflows": workflows,
        "dbos_workflows": dbos_workflows,
        "total": len(workflow_state.workflows)
    }


@router.get("/{workflow_id}")
async def get_workflow_status(workflow_id: str) -> Dict[str, Any]:
    """Get detailed status of a specific workflow"""
    # Check our cache first
    if workflow_id not in workflow_state.workflows:
        # Try DBOS
        try:
            dbos_status = DBOS.retrieve_workflow(workflow_id)
            return {
                "workflow_id": workflow_id,
                "source": "dbos",
                "status": dbos_status.status,
                "result": dbos_status.get_result() if dbos_status.status == "SUCCESS" else None
            }
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {str(e)}")
    
    # Get from our cache
    workflow_data = workflow_state.workflows[workflow_id]
    state_history = workflow_state.state_history.get(workflow_id, [])
    current_state = workflow_state.get_current_state(workflow_id)
    
    # Also try to get DBOS status
    dbos_status = None
    try:
        status = DBOS.retrieve_workflow(workflow_id)
        dbos_status = {
            "status": status.status,
            "result": status.get_result() if status.status == "SUCCESS" else None
        }
    except Exception:
        pass
    
    return {
        "workflow_id": workflow_id,
        "agent_id": workflow_data.get("agent_id"),
        "module_name": workflow_data.get("module_name"),
        "current_state": current_state,
        "created_at": workflow_data.get("created_at"),
        "state_history": state_history,
        "request": workflow_data.get("request"),
        "dbos_status": dbos_status
    }


@router.post("/{workflow_id}/cancel")
async def cancel_workflow(workflow_id: str) -> Dict[str, Any]:
    """Cancel a running workflow"""
    # Update our cache
    if workflow_id in workflow_state.workflows:
        workflow_state.set_state(workflow_id, "FAILED", cancelled=True)
    
    # Try to cancel in DBOS
    try:
        DBOS.cancel_workflow(workflow_id)
        return {
            "workflow_id": workflow_id,
            "status": "FAILED",
            "message": "Workflow cancelled successfully"
        }
    except Exception as e:
        return {
            "workflow_id": workflow_id,
            "status": "FAILED",
            "message": f"Cancelled in cache. DBOS error: {str(e)}"
        }