import asyncio

from fastapi import FastAPI
from opentelemetry.trace import SpanKind
from sqlmodel import Field, Session, SQLModel, create_engine, select


from nats_observe.config import NATSotelSettings
from nats_observe.client import Client as NATSotel

from server.agent.main import router as agent_router, nats_connect, cleanup_agents
from server.pipeline.main import router as pipeline_router, runs_monitor, check_opensearch_connections


SERVERS = ["nats://192.168.19.157:4222"]
settings = NATSotelSettings(service_name="server", servers=SERVERS, )
nc: NATSotel = NATSotel(settings, kind=SpanKind.SERVER)
engine = create_engine("postgresql+psycopg2://pguser:pgpassword@postgres/pg")


async def lifespan(app: FastAPI):
    await nc.connect(settings.servers, name="server", verbose=True, reconnect_time_wait=0)


    asyncio.create_task(nats_connect(nc))
    asyncio.create_task(cleanup_agents())
    asyncio.create_task(runs_monitor(nc))

    await check_opensearch_connections()
    SQLModel.metadata.create_all(engine)


    yield

app = FastAPI(title="Server", version="1.0", lifespan=lifespan)



# Include the router into the main application
app.include_router(agent_router)
app.include_router(pipeline_router)

@app.get("/")
async def root():
    return {
        "status": "ok",
    }

