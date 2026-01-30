import asyncio
import os
import json
import time
import getpass
import pwd, grp
import socket
import traceback
import platform

from aiori_agent.base import BaseWorker
from aiori_agent.utils import check_package_availability, install_package

from nats.aio.msg import Msg

from heartbeat.utils import _safe_get_user_info, _safe_get_system_info, _safe_get_network_info, _safe_agent_version, _safe_loaded_modules
from heartbeat.model import Agent, HeartbeatModel

class HeartbeatModule(BaseWorker):
    """
    A minimal working module that echoes heartbeat messages.
    """

    def __init__(self, name: str, agent, nc, logger, shared):
        super().__init__(name, agent, nc, logger, shared)

        self.sub_out = f"agent.{self.name}"
        self.sub_err = f"agent.{self.name}.error"

        self.interval = shared.get("interval", 2)  # seconds
        self.tags = shared.get("tags", {})

    async def setup(self):
        # if not check_package_availability("netifaces"):
        #     install_package("netifaces")
        #     await asyncio.sleep(5)
        # return check_package_availability("netifaces")
        return True

    async def run(self):
        """
        Subscribes to the input subject and echoes data to output.
        """

        self.logger.info(f"{self.name}: Broascasting on {self.sub_out}")
        await self.nc.publish(
            "agent.notif",
            json.dumps({"message": f"Started module", "name": self.name}).encode(),
        )

        self.logger.info(f"{self.name}: Starting heartbeat every {self.interval}s")

        try:
            while self.running:
                await self._send_heartbeat()
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError as cex:
            self.logger.warning(f"{self.name}: Cancelled")
            await self.nc.publish(
                "agent.notif",
                json.dumps({"message": f"Stopped module", "name": self.name}).encode(),
            )
        except Exception as exception:
            self.logger.exception(f"{self.name}: Error in run loop")
            tb = traceback.format_exc()
            error_data = {"module": self.name, "traceback": tb, "error": str(exception)}
            await self.nc.publish(self.sub_err, json.dumps(error_data).encode())

    def _get_agent_info(self) -> Agent:
        """Constructs the complete heartbeat data payload."""
        return Agent(
            id = self.agent.agent_id,
            name = self.agent.agent_name,
            timezone = list(time.tzname),  # Tuple like ('IST', 'IST') or ('EST', 'EDT') - (Non Day Light Saving Timezone, Day Light Saving Timezone)
            hostname = socket.gethostname(),
            pid = os.getpid(),
            user = _safe_get_user_info(self),
            system = _safe_get_system_info(self),
            network = _safe_get_network_info(self),
            modules = _safe_loaded_modules(self)
        )

    async def _send_heartbeat(self):
        # Create a trace group for this module operation
        heartbeat = HeartbeatModel(
            module = self.name,
            timestamp = time.time(),
            agent = self._get_agent_info(),
            tags = self.tags,
        )
        await self.nc.publish(self.sub_out, heartbeat.model_dump_json().encode())
        self.logger.debug(f"{self.name}: Published heartbeat → {self.sub_out}")
