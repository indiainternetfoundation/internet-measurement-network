import json
import sys
import time
import asyncio
import logging
from typing import Annotated, Optional, Type

from nats.aio.msg import Msg

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("agent")


# Abstract class that each module must inherit
class BaseWorker:
    def __init__(self, name, agent, nc, logger, shared):
        self.name = name
        self.agent: "Agent" = agent
        self.nc = nc
        self.running = False
        self.logger = logger.getChild(name)
        self.shared = shared
        self.task = None

        self.sub_in = None
        self.sub_out = None
        self.sub_err = None

    def serializer(self, ) -> Optional[Type["MeasurementQuery"]]:
        # raise NotImplementedError("Worker must implement serializer()")
        return None

    async def setup(self):
        raise NotImplementedError("Worker must implement setup()")

    async def run(self):
        raise NotImplementedError("Worker must implement run()")

    async def __run__(self, crash_handler):
        try:
            self.running = True
            await self.run()
        except Exception as ex:
            self.running = False
            await crash_handler(self.name, ex)

    async def handler_decorator(self, cb):
        def wrapper(msg):
            async def wrapped_and_subbed_callback():
                data = json.loads(msg.data.decode())
                msg_id = data.get("id")  # Ensure 'id' is present for logging
                info = {
                    "query.id": msg_id,
                    "query.name": str(self.name),
                    "query.agent": str(self.agent.agent_id),
                }
                try:
                    await self.nc.publish(self.sub_out, json.dumps({"status": "started", **info}).encode())
                    self.logger.debug(f"Received message with id: {msg_id}")
                    result = await cb(msg)
                    await self.nc.publish(self.sub_out, json.dumps({"status": "completed", **info}).encode())
                    return result
                except Exception as ex:
                    self.logger.exception("Error in handler_decorator")
                    await self.nc.publish(self.sub_err, json.dumps({"status": "error", "error": str(ex), **info}).encode())
                    raise ex
            return wrapped_and_subbed_callback()
        return wrapper

    def start(self, crash_handler):
        self.task = asyncio.create_task(self.__run__(crash_handler=crash_handler))

    async def stop(self, msg="Exclusive stop", timeout=20):
        self.task.cancel(msg=msg)
        ct = time.perf_counter() + timeout
        while self.task and not self.task.done():
            if ct < time.perf_counter():
                raise asyncio.exceptions.TimeoutError()
            await asyncio.sleep(0.1)
        self.running = False
        self.task = None
        return True