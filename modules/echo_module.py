import json
import time
from typing import Optional, Type
from aiori_agent.base import BaseWorker
from nats.aio.msg import Msg
from aiori_agent.model import MeasurementQuery
from pydantic import BaseModel, Field


class EchoQuery(MeasurementQuery):
    message: str = Field(title="Message", description="The message to echo back")


class WorkingModule(BaseWorker):
    """
    A minimal working module that echoes back received messages.
    """

    def __init__(self, name: str, agent, nc, logger, shared):
        super().__init__(name, agent, nc, logger, shared)

        # Use simple naming pattern like the ping module
        self.sub_in = f"agent.{self.agent.agent_id}.working_module.in"
        self.sub_out = f"agent.{self.agent.agent_id}.working_module.out"
        self.sub_err = f"agent.{self.agent.agent_id}.working_module.error"

    def serializer(self) -> Type[MeasurementQuery]:
        return EchoQuery

    async def setup(self):
        return True

    async def run(self):
        """
        Subscribes to the input subject and echoes data to output.
        """
        await self.nc.subscribe(self.sub_in, cb=self.handle)
        self.logger.info(f"{self.name}: Listening on {self.sub_in}")

    async def handle(self, msg: Msg):
        """
        Processes incoming message and sends output.
        """
        workflow_id = None
        try:
            data = msg.data.decode()
            self.logger.debug(f"{self.name}: Received {data}")
            payload = json.loads(data)
            workflow_id = payload.get("workflow_id")  # Extract workflow ID for state tracking
            
            # Report that we're running this specific request
            state_data = {
                "agent_id": self.agent.agent_id,
                "module_name": self.name,
                "state": "RUNNING",
                "workflow_id": workflow_id
            }
            await self.nc.publish("agent.module.state", json.dumps(state_data).encode())
            
            payload["processed_at"] = time.time()
            payload["from_module"] = self.name
            payload["workflow_id"] = workflow_id

            await self.nc.publish(self.sub_out, json.dumps(payload).encode())
            self.logger.debug(f"{self.name}: Published to {self.sub_out}")
            
            # Report completion with workflow ID
            state_data = {
                "agent_id": self.agent.agent_id,
                "module_name": self.name,
                "state": "COMPLETED",
                "workflow_id": workflow_id
            }
            await self.nc.publish("agent.module.state", json.dumps(state_data).encode())
        except Exception as e:
            self.logger.exception(f"{self.name}: Error during handle")
            await self.nc.publish(self.sub_err, str(e).encode())
            
            # Report error with workflow ID
            state_data = {
                "agent_id": self.agent.agent_id,
                "module_name": self.name,
                "state": "FAILED",
                "error_message": str(e),
                "workflow_id": workflow_id
            }
            await self.nc.publish("agent.module.state", json.dumps(state_data).encode())
