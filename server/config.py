"""
Server configuration module
Centralizes all configuration settings and environment variables
"""
import os
from typing import List


class ServerConfig:
    """Centralized server configuration"""
    
    # NATS configuration
    NATS_URL: List[str] = [os.environ.get("NATS_URL", "nats://localhost:4222")]
    HEARTBEAT_SUBJECT: str = "agent.heartbeat_module"
    HEARTBEAT_INTERVAL: int = 5
    HEARTBEAT_TIMEOUT: int = HEARTBEAT_INTERVAL * 2
    
    # OpenTelemetry endpoints
    OTLP_TRACE_ENDPOINT: str = os.environ.get("OTLP_TRACE_ENDPOINT", "otel-collector:4317")
    OTLP_METRICS_ENDPOINT: str = os.environ.get("OTLP_METRICS_ENDPOINT", "otel-collector:4317")
    OTLP_LOGS_ENDPOINT: str = os.environ.get("OTLP_LOGS_ENDPOINT", "otel-collector:4317")
    
    # Database
    DBOS_SYSTEM_DATABASE_URL: str = os.environ.get("DBOS_SYSTEM_DATABASE_URL", "sqlite:///db/data.db")
    
    # ClickHouse configuration
    CLICKHOUSE_HOST: str = os.environ.get("CLICKHOUSE_HOST", "localhost")
    CLICKHOUSE_PORT: int = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
    CLICKHOUSE_DATABASE: str = os.environ.get("CLICKHOUSE_DATABASE", "imn")
    CLICKHOUSE_USERNAME: str = os.environ.get("CLICKHOUSE_USERNAME", "admin")
    CLICKHOUSE_PASSWORD: str = os.environ.get("CLICKHOUSE_PASSWORD", "")


# Global configuration instance
config = ServerConfig()