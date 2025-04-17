import json
import time
import re
from urllib.request import urlopen
from urllib.error import URLError
import ssl
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

# Constants
HEALTHZ_ENDPOINT = "healthz"

def is_healthz_endpoint(system: str, endpoint: str) -> bool:
    return system == "core" and endpoint == HEALTHZ_ENDPOINT

@dataclass
class Healthz:
    status: str
    error: Optional[str] = None
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Healthz':
        return Healthz(
            status=data.get("status", ""),
            error=data.get("error", None)
        )

@dataclass
class Metric:
    name: str
    labels: Dict[str, str]
    value: float

class HealthzCollector:
    def __init__(self, servers: List[str]):
        self.http_client = None  # Using default urllib
        self.servers = [{"URL": f"{s}/{HEALTHZ_ENDPOINT}"} for s in servers]
        
    def fetch(self) -> List[Metric]:
        metrics = {}
        
        for i, server in enumerate(self.servers):
            server_id = f"server_{i+1}"  # Generate a simple server ID
            http_get_error = False
            health = None
            
            try:
                response = self._get_metric_url(server["URL"])
                health_data = json.loads(response.read().decode())
                health = Healthz.from_dict(health_data)
                
                # Keep the existing metric behaving the same
                status = 1.0
                if health.status == "ok":
                    status = 0.0
                status_value = 1.0 if health.status == "ok" else 0.0
                
                metrics.append(Metric(
                    name="core_healthz_status",
                    labels={"server_id": server_id},
                    value=status_value
                ))
                
                
            except URLError as e:
                print(f"Error fetching metrics from server at {server['URL']}: {e}")
                # Server unreachable metric
                metrics.append(Metric(
                    name="core_healthz_status_value",
                    labels={"server_id": server_id, "value": "unreachable"},
                    value=0.0
                ))
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON from server at {server['URL']}: {e}")
                metrics.append(Metric(
                    name="core_healthz_status_value",
                    labels={"server_id": server_id, "value": "invalid_response"},
                    value=0.0
                ))
            except Exception as e:
                print(f"An unexpected error occurred while processing server at {server['URL']}: {e}")
                metrics.append(Metric(
                    name="core_healthz_status_value",
                    labels={"server_id": server_id, "value": "error"},
                    value=0.0
                ))
        
        return metrics
    
    def _get_metric_url(self, url: str):
        context = ssl._create_unverified_context()
        return urlopen(url, context=context)