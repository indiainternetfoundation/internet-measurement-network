import asyncio
import json
import uuid

from nats_observe.config import NATSotelSettings
from nats_observe.client import Client as NATSotel

from datamodel_code_generator.parser.jsonschema import JsonSchemaParser

IN_SUB = "agent.f7c34015-2b5c-4b95-b1bf-5e5391241dac.in"
OUT_SUB = "agent.f7c34015-2b5c-4b95-b1bf-5e5391241dac.out"

async def sub_cb(msg):
    print(msg)
    pass

async def main():
    url: list[str] = ["nats://192.168.0.112:4222"]

    settings = NATSotelSettings(service_name="server", servers=url)

    nc: NATSotel = NATSotel(settings)

    await nc.connect(settings.servers, name="server", verbose=True, reconnect_time_wait=0)

    await nc.subscribe(OUT_SUB, sub_cb)

    ping_request = {
        "id": str(uuid.uuid4()),
        "target": "8.8.8.8",
        "count": 10
    }
    await nc.publish(IN_SUB, json.dumps(ping_request).encode())

    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())