"""
NATS message handlers - processes incoming NATS messages
"""
import json
import sys
import importlib
from datetime import datetime, timezone
from typing import Dict, Any

from nats.aio.msg import Msg

from main import (
    agent_cache, workflow_state, heartbeat_sampler, 
    CLICKHOUSE_AVAILABLE, safe_clickhouse_insert,
    setup_agent_subscriptions_workflow
)


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
            return manager
    
    return None


async def handle_heartbeat(msg: Msg) -> None:
    """Process agent heartbeat messages"""
    try:
        data = json.loads(msg.data.decode())
        agent_id = data["agent"]["id"]
        hostname = data["agent"]["hostname"]
        print(f"[Heartbeat] Received heartbeat from {agent_id} ({hostname})")
        
        # Update agent cache
        previous_config = None
        if agent_id in agent_cache.agents:
            previous_config = agent_cache.agents[agent_id].config
        
        agent = agent_cache.update_heartbeat(agent_id, hostname, data)
        print(f"[Heartbeat] Updated agent cache for {agent_id}, total heartbeats: {agent.total_heartbeats if agent else 0}")
        
        # Push heartbeat data to ClickHouse if available
        current_manager = get_clickhouse_manager()
        print(f"[Heartbeat] Processing heartbeat for {agent_id}, ClickHouse available: {CLICKHOUSE_AVAILABLE}, manager: {current_manager is not None}")
        if CLICKHOUSE_AVAILABLE and current_manager:
            try:
                # Prepare heartbeat data for ClickHouse
                clickhouse_data = {
                    "agent_id": agent_id,
                    "agent_name": data["agent"].get("name", ""),
                    "hostname": hostname,
                    "timestamp": datetime.now(timezone.utc),
                    "alive": True,
                    "total_heartbeats": agent.total_heartbeats if agent else 0,
                    "config": data,
                    # Default load average values
                    "load_avg_1m": 0.0,
                    "load_avg_5m": 0.0,
                    "load_avg_15m": 0.0,
                }
                
                # Add system metrics if available
                if "agent" in data and "user" in data["agent"]:
                    user_data = data["agent"]["user"]
                    if "loadavg" in user_data:
                        loadavg = user_data["loadavg"]
                        # Handle different loadavg data structures safely
                        try:
                            # loadavg is likely a list/tuple [1m, 5m, 15m] or dict
                            if isinstance(loadavg, (list, tuple)) and len(loadavg) >= 3:
                                clickhouse_data["load_avg_1m"] = float(loadavg[0])
                                clickhouse_data["load_avg_5m"] = float(loadavg[1])
                                clickhouse_data["load_avg_15m"] = float(loadavg[2])
                            elif isinstance(loadavg, dict):
                                # Handle both field naming conventions
                                clickhouse_data["load_avg_1m"] = float(loadavg.get("1m", loadavg.get("field_1m", 0.0)))
                                clickhouse_data["load_avg_5m"] = float(loadavg.get("5m", loadavg.get("field_5m", 0.0)))
                                clickhouse_data["load_avg_15m"] = float(loadavg.get("15m", loadavg.get("field_15m", 0.0)))
                        except (TypeError, ValueError, IndexError, KeyError) as e:
                            # If there's any issue with loadavg data, use defaults
                            print(f"[Heartbeat] Warning: Could not parse loadavg data: {e}")
                            clickhouse_data["load_avg_1m"] = 0.0
                            clickhouse_data["load_avg_5m"] = 0.0
                            clickhouse_data["load_avg_15m"] = 0.0
                
                # Use heartbeat sampler to avoid inserting every heartbeat
                if heartbeat_sampler.should_insert_heartbeat(agent_id):
                    safe_clickhouse_insert("heartbeat insertion", current_manager.insert_heartbeat, clickhouse_data)
                else:
                    print(f"[HeartbeatSampler] Skipping heartbeat insertion for {agent_id} (too soon)")
            except Exception as e:
                print(f"[ClickHouse] Error inserting heartbeat data: {e}")
        
        # If config changed or new agent, resubscribe
        if previous_config != data:
            print(f"[Subscription] Config changed for {agent_id}, resubscribing...")
            try:
                module_specs = data.get("agent", {}).get("modules", {}).get("spec", {})
                await setup_agent_subscriptions_workflow(agent_id, module_specs)
            except Exception as e:
                print(f"[Subscription] Error resubscribing for {agent_id}: {e}")
                
    except Exception as e:
        print(f"[Heartbeat] Error processing heartbeat: {e}")


async def handle_module_state(msg: Msg) -> None:
    """
    Process module state change messages from agents.
    Maps agent states to workflow states: RUNNING, COMPLETED, FAILED
    """
    try:
        data = json.loads(msg.data.decode())
        agent_id = data["agent_id"]
        module_name = data["module_name"]
        state = data["state"]
        workflow_id = data.get("workflow_id")
        
        if not workflow_id:
            print(f"[ModuleState] No workflow_id in state message, skipping")
            return
        
        # Check if workflow exists
        if workflow_id not in workflow_state.workflows:
            print(f"[ModuleState] Unknown workflow: {workflow_id}")
            return
        
        # Map agent states to our 3 workflow states
        state_mapping = {
            "STARTED": "RUNNING",
            "RUNNING": "RUNNING",
            "COMPLETED": "COMPLETED",
            "ERROR": "FAILED",
            "FAILED": "FAILED"
        }
        
        mapped_state = state_mapping.get(state.upper())
        if not mapped_state:
            print(f"[ModuleState] Unknown state '{state}', ignoring")
            return
        
        # Update workflow state
        workflow_state.set_state(
            workflow_id,
            mapped_state,
            agent_id=agent_id,
            module_name=module_name,
            agent_state=state,
            error_message=data.get("error_message")
        )
        
        # Push module state data to ClickHouse if available
        current_manager = get_clickhouse_manager()
        if CLICKHOUSE_AVAILABLE and current_manager:
            try:
                # Prepare state data for ClickHouse
                clickhouse_data = {
                    "workflow_id": workflow_id,
                    "agent_id": agent_id,
                    "module_name": module_name,
                    "state": mapped_state,
                    "timestamp": datetime.now(timezone.utc),
                    "error_message": data.get("error_message"),
                    "details": {
                        "agent_state": state,
                        "original_data": data
                    }
                }
                
                # Insert into ClickHouse using safe wrapper
                safe_clickhouse_insert("module state insertion", current_manager.insert_module_state, clickhouse_data)
            except Exception as e:
                print(f"[ClickHouse] Error inserting module state data: {e}")
        
    except Exception as e:
        print(f"[ModuleState] Error processing state: {e}")


async def result_handler(msg: Msg):
    """Handler for module results - updates workflow state"""
    try:
        data = json.loads(msg.data.decode())
        workflow_id = data.get("workflow_id")
        
        if not workflow_id:
            print(f"[Result] Received result without workflow_id, skipping")
            return
        
        # Check if workflow exists
        if workflow_id not in workflow_state.workflows:
            print(f"[Result] Unknown workflow: {workflow_id}")
            return
        
        # Update workflow state based on success
        success = data.get("success", True)
        final_state = "COMPLETED" if success else "FAILED"
        workflow_state.set_state(workflow_id, final_state, result_received=True)
        
        # Push measurement data to ClickHouse if available
        current_manager = get_clickhouse_manager()
        if CLICKHOUSE_AVAILABLE and current_manager:
                try:
                    # Get workflow information
                    workflow_data = workflow_state.workflows.get(workflow_id, {})
                    agent_id = workflow_data.get("agent_id", "")
                    
                    # Get agent information
                    agent_info = agent_cache.get(agent_id)
                    
                    # Prepare measurement data for ClickHouse
                    try:
                        created_at_str = workflow_data.get("created_at")
                        created_at = datetime.fromisoformat(created_at_str) if created_at_str else datetime.now(timezone.utc)
                    except (ValueError, TypeError):
                        created_at = datetime.now(timezone.utc)
                        print(f"[ClickHouse] Warning: Invalid created_at format for workflow {workflow_id}, using current time")
                    
                    clickhouse_data = {
                        "workflow_id": workflow_id,
                        "agent_id": agent_id,
                        "module_name": workflow_data.get("module_name", ""),
                        "created_at": created_at,
                        "completed_at": datetime.now(timezone.utc),
                        "measurement_data": data,
                        "success": success,
                        "request_data": workflow_data.get("request", {})
                    }
                    
                    # Add agent metadata if available
                    if agent_info:
                        clickhouse_data["agent_hostname"] = agent_info.hostname
                        clickhouse_data["agent_name"] = agent_info.config.get("agent", {}).get("name", "")
                        
                        # Add more agent metadata from heartbeat data if available
                        agent_config = agent_info.config
                        if "agent" in agent_config:
                            agent_data = agent_config["agent"]
                            if "user" in agent_data:
                                user_data = agent_data["user"]
                                clickhouse_data["user_name"] = user_data.get("user", "")
                                clickhouse_data["user_uid"] = user_data.get("uid", 0)
                                clickhouse_data["user_gid"] = user_data.get("gid", 0)
                                clickhouse_data["user_home_dir"] = user_data.get("home_dir", "")
                                clickhouse_data["user_shell"] = user_data.get("shell", "")
                            
                            if "system" in agent_data:
                                system_data = agent_data["system"]
                                clickhouse_data["system_machine"] = system_data.get("machine", "")
                                clickhouse_data["system_node_name"] = system_data.get("node_name", "")
                                clickhouse_data["system_platform"] = system_data.get("platform", "")
                                clickhouse_data["system_processor"] = system_data.get("processor", "")
                                clickhouse_data["system_release"] = system_data.get("release", "")
                                clickhouse_data["system_version"] = system_data.get("version", "")
                            
                            if "network" in agent_data:
                                clickhouse_data["network_interfaces"] = agent_data["network"]
                            
                            if "pid" in agent_data:
                                clickhouse_data["agent_pid"] = agent_data["pid"]
                    
                    # Insert into ClickHouse using safe wrapper
                    safe_clickhouse_insert("measurement insertion", current_manager.insert_measurement, clickhouse_data)
                except Exception as e:
                    print(f"[ClickHouse] Error inserting measurement data: {e}")
            
    except Exception as e:
        print(f"[ResultHandler] Error processing message: {e}")