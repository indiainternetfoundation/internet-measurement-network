import json
import time
import logging
import asyncio
from typing import Any, Optional, Type
from ipaddress import IPv4Address, IPv6Address

from aiori_agent.agent import Agent
from aiori_agent.base import BaseWorker

from nats.aio.client import Client as NATS
from nats.aio.msg import Msg

from aiori_agent.model import Hostname, Domain, MeasurementQuery
from aiori_agent.utils import check_package_availability, install_package

from pydantic import BaseModel, Field


class PingQuery(MeasurementQuery):
    host: IPv4Address | IPv6Address | Hostname | Domain = Field(title="Host", description="This field requires either the IP Address, Hostname or the FQDN of the host system to ping", examples=["8.8.8.8", "1.1.1.1"])
    count: int = Field(default=3, title="Count", description="How many times will the host be pinged for measurement")
    port: int = Field(default=80, title="Port", description="Which port to ping to")

class PingModule(BaseWorker):
    """
    Ping module with direct agent targeting capability
    """

    def __init__(
        self,
        name: str,
        agent: Agent,
        nc: NATS,
        logger: logging.Logger,
        shared: dict[str, Any],
    ):
        super().__init__(name, agent, nc, logger, shared)
        # Use simple naming pattern like the working module
        self.sub_in = f"agent.{self.agent.agent_id}.in"
        self.sub_out = f"agent.{self.agent.agent_id}.out"
        self.sub_err = f"agent.{self.agent.agent_id}.error"
        self.subscription = None

    def serializer(self, ) -> Type[MeasurementQuery]:
        return PingQuery

    async def setup(self):
        if not check_package_availability("icmplib"):
            install_package("icmplib")

        await asyncio.sleep(5)
        return check_package_availability("icmplib")

    async def run(self):
        """
        Subscribes to the input subject and starts handling ping requests.
        """
        try:
            self.subscription = await self.nc.subscribe(self.sub_in, cb=self.handle)
            self.logger.info(f"{self.name}: Listening on {self.sub_in}")
        except Exception as e:
            self.logger.error(f"{self.name}: Failed to subscribe to {self.sub_in}: {e}")
            raise

    async def handle(self, msg: Msg):
        """
        Processes incoming ping requests and sends results.
        This operation will be grouped under "ping_module" trace group.
        """
        workflow_id = None
        try:
            # Log raw message for debugging
            self.logger.debug(f"Received raw message: {msg.data.decode()}")

            data = json.loads(msg.data.decode())
            workflow_id = data.get("workflow_id")  # Extract workflow ID for state tracking

            query = PingQuery(**data)
            model_type = PingQuery.model_type()

            # Report that we're running this specific request
            if workflow_id:
                await self._report_state("RUNNING", details={"action": "processing_request"}, request_id=workflow_id)

            # Execute ping
            from icmplib import Host
            try:
                from icmplib import async_ping
                ping_result = await async_ping(
                    address=str(query.host), 
                    count=query.count, 
                    interval=1, 
                    timeout=5
                )

            except Exception as ex:
                from tcping import TCPing
                async_ping = TCPing(
                    host = str(query.host), 
                    port = query.port, 
                    count = query.count, 
                    timeout = 5
                )
                ping_result = await async_ping.ping()

            result = {
                "id": str(query.id),
                "address": ping_result.address,
                "rtts": ping_result.rtts,
                "packets_received": ping_result.packets_received,
                "packets_sent": ping_result.packets_sent,
                "workflow_id": workflow_id
            }

            self.logger.info(f"{self.name}: Ping completed with result: {result}")
            await self.nc.publish(self.sub_out, json.dumps(result).encode("utf-8"))
            self.logger.debug(f"{self.name}: Published to {self.sub_out}")

            # Report completion with workflow ID
            if workflow_id:
                await self._report_state("COMPLETED", details={"action": "request_completed"}, request_id=workflow_id)

        except Exception as e:
            self.logger.exception(f"{self.name}: Error during handle")
            await self.nc.publish(self.sub_err, str(e).encode("utf-8"))
            
            # Report error with workflow ID
            if workflow_id:
                await self._report_state("FAILED", str(e), details={"action": "request_failed"}, request_id=workflow_id)

