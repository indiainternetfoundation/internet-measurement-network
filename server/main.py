import asyncio

from fastapi import FastAPI
from sqlmodel import SQLModel

from server.core.connections import nc, settings, engine
from server.agent.main import router as agent_router, nats_connect, cleanup_agents
from server.pipeline.main import router as pipeline_router, runs_monitor, check_opensearch_connections

async def lifespan(app: FastAPI):
    await nc.connect(settings.servers, name="server", verbose=True, reconnect_time_wait=0)

    asyncio.create_task(nats_connect(nc))
    asyncio.create_task(cleanup_agents())
    asyncio.create_task(runs_monitor(nc))

    await check_opensearch_connections()
    SQLModel.metadata.create_all(engine)

    yield

app = FastAPI(
    title="IMN Management Server", 
    summary="A simple API to manage the Aiori IMN system.",
    description="This API is used to manage the IMN system, including agents and data pipelines.",
    version="1.0", 
    root_path="/api/v1", 
    lifespan=lifespan
)

# Include the router into the main application
app.include_router(agent_router)
app.include_router(pipeline_router)

@app.get("/")
async def root():
    return {
        "status": "ok",
        "nc": nc.stats,
        "message": "Welcome to the IMN Management Server!",
        # "engine": engine.raw_connection
    }

