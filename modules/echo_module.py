import json
import time
from aiori_agent.base import BaseWorker
from nats.aio.msg import Msg


class WorkingModule(BaseWorker):
    """
    A minimal working module that echoes back received messages.
    """

    def __init__(self, name: str, agent, nc, logger, shared):
        super().__init__(name, agent, nc, logger, shared)

        self.sub_in = f"agent.{self.name}.in"
        self.sub_out = f"agent.{self.name}.out"
        self.sub_err = f"agent.{self.name}.error"

    async def setup(self):
        return True

    async def run(self):
        """
        Subscribes to the input subject and echoes data to output.
        """
        await self.nc.subscribe(self.sub_in, cb=await self.handler_decorator(self.handle))
        self.logger.info(f"{self.name}: Listening on {self.sub_in}")

    async def handle(self, msg: Msg):
        """
        Processes incoming message and sends output.
        """
        try:
            data = msg.data.decode()
            self.logger.debug(f"{self.name}: Received {data}")
            payload = json.loads(data)
            payload["processed_at"] = time.time()
            payload["from_module"] = self.name

            await self.nc.publish(self.sub_out, json.dumps(payload).encode())
            self.logger.debug(f"{self.name}: Published to {self.sub_out}")
        except Exception as e:
            self.logger.exception(f"{self.name}: Error during handle")
            await self.nc.publish(self.sub_err, str(e).encode())
