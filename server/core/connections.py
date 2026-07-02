from opentelemetry.trace import SpanKind
from sqlmodel import create_engine

from nats_observe.config import NATSotelSettings
from nats_observe.client import Client as NATSotel

settings = NATSotelSettings(service_name="server", )
nc: NATSotel = NATSotel(settings, kind=SpanKind.SERVER)
engine = create_engine("postgresql+psycopg2://pguser:pgpassword@postgres/pg")

