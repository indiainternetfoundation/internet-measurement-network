import asyncio


from nats_observe.config import NATSotelSettings
from nats_observe.client import Client as NATSotel
from nats.aio.client import Client as NATS

from .base import logger
from .config import settings
from .module_manager import ModuleManager


class NatsClient:
    """
    Manages a shared NATS connection using async context management.
    """

    def __init__(
        self,
        name: str,
        url: str = settings.nats_url,
    ):
        self.name: str = name
        self.url: list[str] = url.split(";")
        otel_settings = NATSotelSettings(
            service_name=self.name,
            servers=self.url,
            otlp_trace_endpoint=settings.otlp_trace_endpoint,
            otlp_logs_endpoint=settings.otlp_logs_endpoint
        )
        # logger = logging.getLogger('server')
        self.nc: NATSotel = NATSotel(otel_settings)

    async def __aenter__(self):
        await self.nc.connect(
            servers=self.url,
            error_cb=self.error_cb,
            closed_cb=self.closed_cb,
            disconnected_cb=self.disconnected_cb,
            discovered_server_cb=self.disconnected_server_cb,
            reconnected_cb=self.reconnected_cb,
            name=self.name,
            pedantic=True,
            verbose=True,
            allow_reconnect=True,
            # connect_timeout = ,
            # reconnect_time_wait = ,
            # max_reconnect_attempts = ,
            # user = ,
            # password = ,
            # user_credentials = ,
            # user_jwt_cb = ,
            # signature_cb=
        )
        return self.nc

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.nc.is_connected:
            await self.nc.drain()

    async def close(self):
        if self.nc.is_connected:
            await self.nc.close()

    async def disconnected_cb(
        self,
    ):
        logger.warning("Got disconnected!")

    async def disconnected_server_cb(
        self,
    ):
        logger.warning("Got disconnected server!")

    async def reconnected_cb(
        self,
    ):
        logger.warning(f"Got reconnected to {self.nc.connected_url}")

    async def error_cb(self, ex: Exception):
        logger.error(f"There was an error: {ex}")

    async def closed_cb(
        self,
    ):
        logger.warning("Connection is closed")


class Agent:
    """
    Main controller of the system: coordinates NATS, modules, recovery.
    """

    def __init__(self):
        self.agent_id = settings.agent_id
        self.agent_name = settings.agent_name
        self.manager = None
        self.nc = None

    async def start(self):
        """
        Start NATS and load modules.
        """
        async with NatsClient(name=self.agent_name) as nc:
            self.nc = nc
            self.manager = ModuleManager(self, nc)
            await self.manager.start_all()
            await asyncio.Future()

    async def _keep_running(self):
        """
        Keeps the agent running.
        """
        while True:
            await asyncio.sleep(3600)
