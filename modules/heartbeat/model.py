
from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel, Field

class ModuleSpecification(BaseModel):
    input_schema: Dict[str, Any]

    input_subject: str
    output_subject: str
    error_subject: str


class Modules(BaseModel):
    modules: List[str]
    spec: Dict[str, ModuleSpecification]

class NetworkInterface(BaseModel):
    ipv4: List
    ipv6: List[str]
    mac: List[str]

class System(BaseModel):
    machine: str
    node_name: str
    platform: str
    processor: str
    release: str
    system: str
    version: str

class Loadavg(BaseModel):
    field_15m: float = Field(..., alias='15m')
    field_1m: float = Field(..., alias='1m')
    field_5m: float = Field(..., alias='5m')

class User(BaseModel):
    gecos: str
    gid: int
    groups: List[str]
    home_dir: str
    shell: str
    uid: int
    user: str
    working_dir: str
    loadavg: Optional[Loadavg] = None

class Agent(BaseModel):
    hostname: str
    id: str
    modules: Modules
    name: str
    network: Mapping[str, NetworkInterface | Mapping[str, str]]
    pid: int
    system: System
    timezone: List[str]
    user: User

class HeartbeatModel(BaseModel):
    agent: Agent
    module: str
    tags: Dict[str, Any]
    timestamp: float
