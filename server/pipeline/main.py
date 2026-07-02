import json, uuid
from datetime import datetime

from nats.aio.msg import Msg

from fastapi import APIRouter
from sqlmodel import Session, select

from opensearchpy import OpenSearch

from server.pipeline.models.pipeline import OpensearchDataPipeline
from server.pipeline.models.measurement import MeasurementState, Status
from ..core.connections import engine

OUTPUT_SUBJECT = "agent.*.out"

osdp = OpensearchDataPipeline(
    host = "192.168.19.157", port = 9200,
    username = "admin", password = "My_password_123!@#",
    use_ssl = True,
    verify_certs = False,
    ssl_assert_hostname = False,
    ssl_show_warn = False,

    index = "aiori-imn",
    subject = "",
)

__PIPELINE = [
    {
        "ospd": osdp,
        "client": OpenSearch(
            hosts = [{'host': osdp.host, 'port': osdp.port}],
            http_compress = True, # enables gzip compression for request bodies
            http_auth = (osdp.username, osdp.password),
            use_ssl = osdp.use_ssl,
            verify_certs = osdp.verify_certs,
            ssl_assert_hostname = osdp.ssl_assert_hostname,
            ssl_show_warn = osdp.ssl_show_warn,
        )
    },
]

async def runs_monitor(nc):
    async def monitor_handler(msg: Msg):
        try:
            data = json.loads(msg.data.decode())
            measurement_query_id = data.get("query.id")

            if measurement_query_id:
                with Session(engine) as session:
                    # Measurement Status
                    measurement_state = MeasurementState(
                        query_id=uuid.UUID(data.get("query.id")),
                        query_type=data.get("query.name"),
                        query_agent=data.get("query.agent"),
                        status=Status(data.get("status", "running"))
                    )
                    session.add(measurement_state)

                    # Measurement Data
                    if "status" not in data:
                        try:
                            for pipeline in __PIPELINE:
                                ospd : OpensearchDataPipeline = pipeline["ospd"]
                                client : OpenSearch = pipeline["client"]

                                response = client.index(
                                    index = "-".join([osdp.index, datetime.now().strftime("%Y.%m.%d")]),
                                    body = data,
                                    id = measurement_query_id,
                                    refresh = True
                                )

                        except Exception as ex:
                            print("Error", ex)
                            pass
                    
                    session.commit()
        except Exception as e:
            print("[Run Monitor] Error parsing run update:", e)

    await nc.subscribe(OUTPUT_SUBJECT, cb=monitor_handler)

async def check_opensearch_connections():
    for pipe in __PIPELINE:
        client : OpenSearch = pipe["client"]
        if client.ping():
            pass
        else:
            # Exception as Opensearch is unreachable
            pass
        try:
            client.info()
        except Exception as ex:
            # Exception as Opensearch is reachable but cannot connect
            pass

# Create a router instead of a FastAPI instance
router = APIRouter(prefix="/pipeline", tags=["pipeline"])

@router.get("/runs/status/{measurement_id}")
async def get_run_status(measurement_id: uuid.UUID):
    """
    Get the status of a specific run by its ID.
    """

    measurement_history = []
    with Session(engine) as session:
        statement = select(MeasurementState).where(MeasurementState.query_id == measurement_id) \
            .order_by(MeasurementState.created_at.desc())
        
        with Session(engine) as session:
            for history in session.exec(statement):
                measurement_history.append({
                    "status": history.status.value,
                    "timestamp": history.created_at.isoformat()
                })
            current_state = session.exec(statement).first()
    return {
        "measurement_id": measurement_id,
        "status": current_state.status if current_state else None,
        "history": measurement_history if current_state else []
    }