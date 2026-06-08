import json
import time
import random
import asyncio
from aiori_agent.base import BaseWorker
from nats.aio.msg import Msg


class FaultyModule(BaseWorker):
    """
    A test module to simulate failure, crash, or delay based on input.
    """

    def __init__(self, name: str, agent, nc, logger, shared):
        super().__init__(name, agent, nc, logger, shared)

        self.sub_in = f"agent.{self.name}.in"
        self.sub_out = f"agent.{self.name}.out"
        self.sub_err = f"agent.{self.name}.error"
        self.processed_ids = set()

    async def setup(self):
        return True

    async def run(self):
        await self.nc.subscribe(self.sub_in, cb=await self.handler_decorator(self.handle))
        self.logger.info(f"{self.name}: Listening on {self.sub_in}")

    async def handle(self, msg: Msg):
        try:
            payload = json.loads(msg.data.decode())
            self.logger.info(f"{self.name}: Received {payload}")

            # Simulate delay
            if payload.get("delay"):
                await asyncio.sleep(payload["delay"])
                self.logger.debug(f"{self.name}: Finished simulated delay")

            # Simulate crash
            if payload.get("crash"):
                raise RuntimeError("Intentional crash triggered.")

            # Simulate duplicate processing (ACID)
            message_id = payload.get("id")
            if message_id and message_id in self.processed_ids:
                self.logger.warning(
                    f"{self.name}: Duplicate message ignored: {message_id}"
                )
                return
            if message_id:
                self.processed_ids.add(message_id)

            # Echo back
            response = {
                "from_module": self.name,
                "processed_at": time.time(),
                "input": payload,
            }
            await self.nc.publish(self.sub_out, json.dumps(response).encode())

        except Exception as e:
            self.logger.exception(f"{self.name}: Failed during handle")
            await self.nc.publish(self.sub_err, str(e).encode())
