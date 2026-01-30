import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import FastAPI, Query, HTTPException
from dbos import DBOS, DBOSConfig, Queue
from nats_observe.config import NATSotelSettings
from nats_observe.client import Client as NATSotel
from nats.aio.msg import Msg
from openapi_schema_validator import validate
from jsonschema.exceptions import ValidationError

# Try to import ClickHouse manager
try:
    from olap.clickhouse_manager import ClickHouseManager
    CLICKHOUSE_AVAILABLE = True
except ImportError:
    CLICKHOUSE_AVAILABLE = False
    print("[Server] ClickHouse manager not available")

from models import AgentInfo, ModuleStateEnum
from db.persistence import PersistenceManager
from config import config


# ============================================================================
# STATE MANAGEMENT
# ============================================================================

from services.workflow_service import WorkflowService
from services.agent_service import AgentService

# Global service instances
workflow_service = WorkflowService()
agent_service = AgentService()



# Import new managers
from subscription_manager import SubscriptionManager
from heartbeat_sampler import HeartbeatSampler

# Global state instances - use the service instances we already created
workflow_state = workflow_service
agent_cache = agent_service

# Subscription manager (will be initialized after NATS connection)
subscription_manager = None

# Heartbeat sampler
heartbeat_sampler = HeartbeatSampler(sample_interval_seconds=30)  # Sample every 30 seconds

# ClickHouse manager
clickhouse_manager = None

def initialize_clickhouse():
    """Initialize ClickHouse connection and tables with proper error handling"""
    global clickhouse_manager
    
    if not CLICKHOUSE_AVAILABLE:
        print("[Server] ClickHouse support not available (clickhouse-connect not installed)")
        return False
    
    try:
        print("[Server] Initializing ClickHouse connection...")
        clickhouse_manager = ClickHouseManager(
            host=config.CLICKHOUSE_HOST,
            port=config.CLICKHOUSE_PORT,
            database=config.CLICKHOUSE_DATABASE,
            username=config.CLICKHOUSE_USERNAME,
            password=config.CLICKHOUSE_PASSWORD
        )
        
        # Try to connect
        if not clickhouse_manager.connect():
            print("[Server] Failed to connect to ClickHouse - analytics will be disabled")
            clickhouse_manager = None
            return False
        
        print("[Server] ClickHouse connected, initializing tables...")
        
        # Try to initialize tables
        if not clickhouse_manager.initialize_tables():
            print("[Server] Failed to initialize ClickHouse tables - analytics will be disabled")
            clickhouse_manager.close()
            clickhouse_manager = None
            return False
        
        print("[Server] ✓ ClickHouse initialized successfully")
        return True
        
    except Exception as e:
        print(f"[Server] ClickHouse initialization error: {e}")
        if clickhouse_manager:
            try:
                clickhouse_manager.close()
            except:
                pass
            clickhouse_manager = None
        return False

# Don't initialize on module load - will be initialized during startup event
# initialize_clickhouse()

# ============================================================================
# HELPER FUNCTIONS FOR CLICKHOUSE OPERATIONS
# ============================================================================

def get_clickhouse_manager():
    """Get the current ClickHouse manager instance"""
    print(f"[Debug] get_clickhouse_manager() called, clickhouse_manager = {clickhouse_manager}")
    return clickhouse_manager

def safe_clickhouse_insert(operation_name: str, insert_func, data: Dict[str, Any]) -> bool:
    """
    Safely attempt to insert data into ClickHouse with error handling
    
    Args:
        operation_name: Name of the operation for logging
        insert_func: The ClickHouse insert function to call
        data: Data dictionary to insert
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not CLICKHOUSE_AVAILABLE or not clickhouse_manager:
        return False
    
    try:
        return insert_func(data)
    except Exception as e:
        print(f"[ClickHouse] {operation_name} failed: {e}")
        return False

# ============================================================================
# DBOS INITIALIZATION
# ============================================================================

dbos_config: DBOSConfig = {
    "name": "agent-server",
    "system_database_url": config.DBOS_SYSTEM_DATABASE_URL,
}
DBOS(config=dbos_config)

# ============================================================================
# NATS CLIENT
# ============================================================================

nats_settings = NATSotelSettings(
    service_name="server",
    servers=config.NATS_URL,
    otlp_trace_endpoint=config.OTLP_TRACE_ENDPOINT,
    otlp_logs_endpoint=config.OTLP_LOGS_ENDPOINT
)
nats_client: NATSotel = NATSotel(nats_settings)

# ============================================================================
# DBOS WORKFLOW STEPS
# ============================================================================

@DBOS.step()
async def validate_agent(agent_id: str) -> AgentInfo:
    """Validate that agent exists and is alive"""
    agent = agent_cache.get(agent_id)
    if not agent or not agent.alive:
        raise HTTPException(status_code=400, detail="Agent is not alive")
    return agent

@DBOS.step()
async def validate_module_schema(
    agent: AgentInfo,
    module_name: str,
    module_request: Dict[str, Any]
) -> Dict[str, Any]:
    """Validate module request against agent's schema"""
    module_specs = agent.config.get("agent", {}).get("modules", {}).get("spec", {})
    
    if module_name not in module_specs:
        raise HTTPException(status_code=404, detail=f"Module '{module_name}' not found")
    
    module_spec = module_specs[module_name]
    
    if not isinstance(module_spec, dict):
        raise HTTPException(status_code=500, detail="Invalid module specification")
    
    try:
        input_schema = module_spec['input_schema']
        if isinstance(input_schema, str):
            input_schema = json.loads(input_schema)
        validate(module_request, input_schema)
    except ValidationError as ex:
        raise HTTPException(status_code=400, detail=f"Validation error: {str(ex)}")
    except json.JSONDecodeError as ex:
        raise HTTPException(status_code=500, detail=f"Invalid schema format: {str(ex)}")
    
    return module_spec

@DBOS.step(retries_allowed=True, max_attempts=3)
async def publish_to_nats(subject: str, message: str) -> None:
    """Publish message to NATS with retries"""
    await nats_client.publish(subject, message.encode())

@DBOS.step(retries_allowed=True, max_attempts=5, backoff_rate=2.0)
async def subscribe_to_nats(subject: str, callback) -> None:
    """Subscribe to NATS subject with retries"""
    await nats_client.subscribe(subject, cb=callback)

# ============================================================================
# DBOS WORKFLOWS
# ============================================================================

@DBOS.workflow()
async def execute_module_workflow(
    agent_id: str,
    module_name: str,
    module_request: Dict[str, Any],
    untracked: bool = False
) -> Dict[str, Any]:
    """
    Durable workflow for module execution coordination.
    Uses workflow_id as the primary identifier throughout.
    States: RUNNING → COMPLETED or FAILED
    """
    workflow_id = getattr(DBOS, 'current_workflow_id', None) or str(uuid.uuid4())
    
    try:
        # Add workflow_id to the request
        module_request["workflow_id"] = workflow_id
        
        # Initialize workflow state (RUNNING)
        workflow_state.create_workflow(
            workflow_id=workflow_id,
            agent_id=agent_id,
            module_name=module_name,
            request=module_request
        )
        
        # Step 1: Validate agent
        agent = await validate_agent(agent_id)
        
        # Step 2: Validate module request
        module_spec = await validate_module_schema(agent, module_name, module_request)
        
        # Step 3: Publish to NATS
        input_subject = module_spec['input_subject']
        if not isinstance(input_subject, str):
            raise HTTPException(status_code=500, detail="Invalid input subject")
        
        await publish_to_nats(input_subject, json.dumps(module_request))
        
        print(f"[Workflow] {workflow_id}: Published to {input_subject}")
        
        return {
            "status": "success",
            "workflow_id": workflow_id,
            "message": "Module execution initiated"
        }
        
    except HTTPException:
        workflow_state.set_state(workflow_id, "FAILED", error="HTTP error")
        raise
    except Exception as ex:
        workflow_state.set_state(workflow_id, "FAILED", error=str(ex))
        raise HTTPException(status_code=500, detail=f"Workflow error: {str(ex)}")

@DBOS.workflow()
async def setup_agent_subscriptions_workflow(
    agent_id: str,
    module_specs: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Durable workflow for setting up agent result subscriptions.
    Ensures reliable subscription to all agent output topics.
    """
    # Use subscription manager to avoid duplicates
    if subscription_manager:
        topics = await subscription_manager.subscribe_to_agent(
            agent_id, module_specs, result_handler
        )
    else:
        # Fallback to original logic if subscription manager not initialized
        topics = set()
        generic_topic = f"agent.{agent_id}.out"
        topics.add(generic_topic)
        
        for module_name, module_config in module_specs.items():
            if "output_subject" in module_config:
                output_topic = module_config["output_subject"]
                if output_topic:
                    topics.add(output_topic)
        
        # Subscribe to all topics
        for topic in topics:
            await nats_client.subscribe(topic, cb=result_handler)
    
    print(f"[Subscription] Agent {agent_id}: {list(topics)}")
    return {"agent_id": agent_id, "subscribed_topics": list(topics)}


# ============================================================================
# NATS HANDLERS
# ============================================================================

from handlers.nats_handlers import handle_heartbeat, handle_module_state, result_handler

# ============================================================================
# BACKGROUND TASKS
# ============================================================================

async def nats_connect_task():
    """Connect to NATS and set up subscriptions"""
    await nats_client.connect(
        nats_settings.servers,
        name="server",
        verbose=True,
        reconnect_time_wait=0
    )
    print(f"[NATS] Connected to {config.NATS_URL}")
    
    # Initialize subscription manager
    global subscription_manager
    subscription_manager = SubscriptionManager(nats_client)
    print("[Subscription] Manager initialized")
    
    # Subscribe to heartbeats and module states
    await nats_client.subscribe(config.HEARTBEAT_SUBJECT, cb=handle_heartbeat)
    await nats_client.subscribe("agent.module.state", cb=handle_module_state)
    print(f"[NATS] Subscribed to control topics")
    
    # Wait for initial heartbeats, then subscribe to existing agents
    await asyncio.sleep(2)
    print(f"[Startup] Subscribing to {len(agent_cache.agents)} existing agents...")
    
    for agent_id, agent in agent_cache.agents.items():
        try:
            module_specs = agent.config.get("agent", {}).get("modules", {}).get("spec", {})
            await setup_agent_subscriptions_workflow(agent_id, module_specs)
            print(f"[Startup] Subscribed to agent: {agent_id}")
        except Exception as e:
            print(f"[Startup] Error subscribing to {agent_id}: {e}")

async def agent_cleanup_task():
    """Periodically mark dead agents"""
    while True:
        agent_cache.mark_dead_agents(config.HEARTBEAT_TIMEOUT)
        await asyncio.sleep(config.HEARTBEAT_INTERVAL)

async def workflow_cleanup_task():
    """Periodically check for stale workflows assigned to dead agents"""
    while True:
        # Check every 30 seconds
        await asyncio.sleep(30)
        try:
            workflow_state.check_stale_workflows(agent_cache)
        except Exception as e:
            print(f"[WorkflowCleanup] Error: {e}")

async def cache_sync_task():
    """Periodically synchronize in-memory cache with database using service methods"""
    while True:
        # Sync every 30 seconds
        await asyncio.sleep(30)
        try:
            # Use the service sync methods which handle the synchronization logic
            agent_cache.sync_with_database()
            workflow_state.sync_with_database()
            
            print(f"[CacheSync] Completed sync - Agents: {len(agent_cache.agents)}, Workflows: {len(workflow_state.workflows)}")

        except Exception as e:
            print(f"[CacheSync] Error during synchronization: {e}")

# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

app = FastAPI(
    title="Agent Server",
    version="2.0",
    description="Workflow-focused agent coordination server"
)

# Execution queue for async workflows
execution_queue = Queue("module_execution", worker_concurrency=10)

@app.on_event("startup")
async def startup_event():
    """Initialize DBOS and background tasks"""
    DBOS.launch()
    print("[DBOS] Launched")
    
    # Initialize ClickHouse connection with retry logic
    for attempt in range(5):
        if initialize_clickhouse():
            break
        print(f"[Server] ClickHouse initialization failed, retrying in 5 seconds... (attempt {attempt + 1}/5)")
        await asyncio.sleep(5)
    else:
        print("[Server] ClickHouse initialization failed after 5 attempts - analytics will be disabled")
    
    asyncio.create_task(nats_connect_task())
    asyncio.create_task(agent_cleanup_task())
    asyncio.create_task(workflow_cleanup_task())
    asyncio.create_task(cache_sync_task())

# ============================================================================
# API ROUTES
# ============================================================================

# Import routers
from routers.agents import router as agents_router
from routers.workflows import router as workflows_router
from routers.debug import router as debug_router
from routers.modules import router as modules_router

# Include routers
app.include_router(agents_router)
app.include_router(workflows_router)
app.include_router(debug_router)
app.include_router(modules_router)

# Root endpoint
@app.get("/")
async def root():
    """Health check and basic stats"""
    return {
        "status": "ok",
        "total_agents": len(agent_cache.agents),
        "alive_agents": len(agent_cache.get_alive()),
        "total_workflows": len(workflow_state.workflows)
    }

