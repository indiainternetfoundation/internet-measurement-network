# import json
import time
import re
import json
from urllib.request import urlopen
from urllib.error import URLError
import ssl
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Any, Optional

# Constants
CONNZ_ENDPOINT = "connz"

def is_connz_endpoint(system: str, endpoint: str) -> bool:
    return system == "core" and (endpoint == CONNZ_ENDPOINT)

@dataclass
class ConnzConnectionResponse:
    cid: int
    kind: str
    type: str
    ip: str
    port: int
    start: datetime
    last_activity: datetime
    rtt: str
    uptime: str
    idle: str
    pending_bytes: float
    in_msgs: float
    out_msgs: float
    in_bytes: float
    out_bytes: float
    subscriptions: int
    name: str
    lang: str
    version: str
    name_tag: str
    account: str
    tls_version: str
    tls_cipher_suite: str

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'ConnzConnectionResponse':
        return ConnzConnectionResponse(
            cid=str(data.get("cid", None)),
            kind=str(data.get("kind", None)),
            type=str(data.get("type", None)),
            ip=str(data.get("ip", None)),
            port=str(data.get("port", 0)),
            start=datetime.fromisoformat(data.get("start")),
            last_activity=datetime.fromisoformat(data.get("last_activity")),
            rtt=ConnzCollector._parse_duration_to_nanoseconds(data.get("rtt")),
            uptime=ConnzCollector._parse_duration_to_nanoseconds(data.get("uptime")),
            idle=ConnzCollector._parse_duration_to_nanoseconds(data.get("idle")),
            pending_bytes=float(data.get("pending_bytes", 0)),
            in_msgs=float(data.get("in_msgs", 0)),
            out_msgs=float(data.get("out_msgs", 0)),
            in_bytes=float(data.get("in_bytes", 0)),
            out_bytes=float(data.get("out_bytes", 0)),
            subscriptions=float(data.get("subscriptions", 0)),
            name=str(data.get("name", None)),
            name_tag=str(data.get("name_tag", "")),
            account=str(data.get("account", None)),
            lang=str(data.get("lang", None)),
            version=str(data.get("version", None)),
            tls_version=str(data.get("tls_version", None)),
            tls_cipher_suite=str(data.get("tls_cipher_suite", None)),
        )

@dataclass
class ConnzResponse:
    server_id: str
    now: datetime
    num_connections: float
    total: float
    offset: float
    limit: float
    connections: List[ConnzConnectionResponse]

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'ConnzResponse':
        return ConnzResponse(
            server_id=data.get("server_id"),
            now=datetime.fromisoformat(data.get("now")),
            num_connections=float(data.get("num_connections", 0)),
            total=float(data.get("total", 0)),
            offset=float(data.get("offset", 0)),
            limit=float(data.get("limit", 0)),
            connections=[ConnzConnectionResponse.from_dict(c) for c in data.get("connections", [])],
        )

@dataclass
class Metric:
    name: str
    labels: Dict[str, str]
    value: float

class ConnzCollector:
    def __init__(self, servers: List[str], auth: bool = False):
        self.http_client = None  # Using default urllib
        self.servers = [{"URL": f"{s}/{CONNZ_ENDPOINT}" + ("?auth=true" if auth else "")} for s in servers]
        self.auth = auth

    def fetch(self) -> List[Metric]:
        metrics = []
        for i, server in enumerate(self.servers):
            server_id = f"server_{i+1}" # Generate a simple server ID
            try:
                response = self._get_metric_url(server["URL"])
                connz_data = json.loads(response.read().decode())
                connz_response = ConnzResponse.from_dict(connz_data)

                total_pending_bytes = 0
                total_subscriptions = 0
                total_in_bytes = 0
                total_out_bytes = 0
                total_in_msgs = 0
                total_out_msgs = 0

                for conn in connz_response.connections:
                    total_pending_bytes += conn.pending_bytes
                    total_subscriptions += conn.subscriptions
                    total_in_bytes += conn.in_bytes
                    total_out_bytes += conn.out_bytes
                    total_in_msgs += conn.in_msgs
                    total_out_msgs += conn.out_msgs
            
                    metrics.append(conn)
            
            except URLError as e:
                print(f"Error fetching metrics from server at {server['URL']}: {e}")
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON from server at {server['URL']}: {e}")
            except Exception as e:
                print(f"An unexpected error occurred while processing server at {server['URL']}: {e}")
        return metrics

    def _get_metric_url(self, url: str):
        context = ssl._create_unverified_context()
        return urlopen(url, context=context)

    @staticmethod
    def _parse_duration_to_nanoseconds(data: Optional[Any]) -> float:
        units = {"ns": 1, "us": 1000, "µs": 1000, "ms": 1000000, "s": 1000000000, "m": 60000000000, "h": 3600000000000}
        if not data:
            return -1
        if isinstance(data, float) or isinstance(data, int):
            return float(data) * 1000 # Assuming already in seconds
        elif isinstance(data, str):
            try:
                value, unit = ConnzCollector.split_value_unit(data)
                return value * units[unit]
            except Exception as e:
                print(f"String '{data}' could not be parsed as duration for rtt: {e}")
                return -1
        else:
            print(f"Unexpected type for rtt duration: {type(data)}, value: {data}")
            return -1

    @staticmethod
    def _parse_go_duration(s: str) -> int:
        units = {"ns": 1, "us": 1000, "µs": 1000, "ms": 1000000, "s": 1000000000, "m": 60000000000, "h": 3600000000000}
        duration = 0
        parts = re.findall(r"([\d.]+)([a-z]+)", s)
        for value, unit in parts:
            if unit in units:
                return (float(value), unit)
            else:
                raise ValueError(f"Unknown unit: {unit}")

    @staticmethod
    def split_value_unit(s):
        match = re.match(r"([0-9.]+)([a-zA-Zµ]+)", s)
        if match:
            value, unit = match.groups()
            return (float(value), unit)
        else:
            raise ValueError("Input must be in the format like '1.32ms'")
