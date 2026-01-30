"""
Debug router - handles debug and monitoring endpoints
"""
from fastapi import APIRouter
from typing import Dict, Any

from main import agent_cache, workflow_state, CLICKHOUSE_AVAILABLE
import sys
import importlib

def get_clickhouse_manager():
    """Dynamically get ClickHouse manager from main module"""
    # Try different module names for the main module
    module_names = ['server.main', 'main']
    
    for module_name in module_names:
        main_module = sys.modules.get(module_name)
        if main_module is None:
            # Try to import it
            try:
                main_module = importlib.import_module(module_name)
            except ImportError:
                continue
        
        # Get the manager from the main module
        manager = getattr(main_module, 'clickhouse_manager', None)
        if manager is not None:
            print(f"[Debug] Found ClickHouse manager in {module_name}")
            return manager
    
    print("[Debug] Could not find ClickHouse manager in any module")
    return None

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/state")
async def debug_state() -> Dict[str, Any]:
    """Debug endpoint to inspect internal state"""
    return {
        "agents": {
            "total": len(agent_cache.agents),
            "alive": len(agent_cache.get_alive()),
            "agent_ids": list(agent_cache.agents.keys())
        },
        "workflows": {
            "total": len(workflow_state.workflows),
            "workflow_ids": list(workflow_state.workflows.keys())[-10:],  # Last 10
            "states": {
                "RUNNING": len([w for w in workflow_state.workflows.keys() 
                               if workflow_state.get_current_state(w) == "RUNNING"]),
                "COMPLETED": len([w for w in workflow_state.workflows.keys() 
                                 if workflow_state.get_current_state(w) == "COMPLETED"]),
                "FAILED": len([w for w in workflow_state.workflows.keys() 
                               if workflow_state.get_current_state(w) == "FAILED"])
            }
        }
    }


@router.get("/clickhouse")
async def debug_clickhouse() -> Dict[str, Any]:
    """Debug ClickHouse connection status"""
    try:
        if not CLICKHOUSE_AVAILABLE:
            return {
                "status": "library_not_available",
                "available": False,
                "message": "clickhouse-connect library not installed"
            }
        
        # Get the current ClickHouse manager dynamically
        manager = get_clickhouse_manager()
        
        if not manager:
            return {
                "status": "not_initialized",
                "available": CLICKHOUSE_AVAILABLE,
                "manager_exists": False
            }
        
        # Get status from manager
        status = manager.get_status()
        
        return {
            "status": "initialized",
            **status
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__
        }