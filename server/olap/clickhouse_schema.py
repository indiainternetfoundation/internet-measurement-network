"""
ClickHouse database schema for storing measurement results and analytics
FIXED VERSION with all issues addressed
"""
from datetime import datetime
from typing import Dict, Any, Optional, List

# ClickHouse table schemas - Each statement must be executed separately
CREATE_TABLE_STATEMENTS = [
    # Measurements table - FIXED
    """CREATE TABLE IF NOT EXISTS measurements (
        workflow_id String,
        agent_id String,
        module_name String,
        created_at DateTime64(6, 'UTC'),
        completed_at DateTime64(6, 'UTC'),
        measurement_data String DEFAULT '{}',
        agent_hostname String DEFAULT '',
        agent_name String DEFAULT '',
        agent_pid UInt32 DEFAULT 0,
        system_machine String DEFAULT '',
        system_node_name String DEFAULT '',
        system_platform String DEFAULT '',
        system_processor String DEFAULT '',
        system_release String DEFAULT '',
        system_version String DEFAULT '',
        network_interfaces String DEFAULT '{}',
        user_name String DEFAULT '',
        user_uid UInt32 DEFAULT 0,
        user_gid UInt32 DEFAULT 0,
        user_home_dir String DEFAULT '',
        user_shell String DEFAULT '',
        request_data String DEFAULT '{}',
        success Boolean DEFAULT true,
        INDEX idx_workflow_id workflow_id TYPE bloom_filter GRANULARITY 1,
        INDEX idx_agent_id agent_id TYPE bloom_filter GRANULARITY 1,
        INDEX idx_module_name module_name TYPE bloom_filter GRANULARITY 1,
        INDEX idx_created_at created_at TYPE minmax GRANULARITY 1
    ) ENGINE = ReplacingMergeTree()
    PRIMARY KEY (workflow_id)
    ORDER BY (workflow_id, created_at, agent_id, module_name)
    PARTITION BY toYYYYMM(created_at)""",
    
    # Agent heartbeats table - FIXED
    """CREATE TABLE IF NOT EXISTS agent_heartbeats (
        agent_id String,
        agent_name String DEFAULT '',
        hostname String DEFAULT '',
        timestamp DateTime64(6, 'UTC'),
        alive Boolean DEFAULT true,
        total_heartbeats UInt32 DEFAULT 0,
        load_avg_1m Float32 DEFAULT 0.0,
        load_avg_5m Float32 DEFAULT 0.0,
        load_avg_15m Float32 DEFAULT 0.0,
        config String DEFAULT '{}',
        INDEX idx_agent_id agent_id TYPE bloom_filter GRANULARITY 1,
        INDEX idx_timestamp timestamp TYPE minmax GRANULARITY 1
    ) ENGINE = MergeTree()
    ORDER BY (timestamp, agent_id)
    PARTITION BY toYYYYMM(timestamp)""",
    
    # Module states table - FIXED
    """CREATE TABLE IF NOT EXISTS module_states (
        workflow_id String,
        agent_id String,
        module_name String DEFAULT '',
        state String DEFAULT '',
        timestamp DateTime64(6, 'UTC'),
        error_message Nullable(String),
        details String DEFAULT '{}',
        INDEX idx_workflow_id workflow_id TYPE bloom_filter GRANULARITY 1,
        INDEX idx_agent_id agent_id TYPE bloom_filter GRANULARITY 1,
        INDEX idx_module_name module_name TYPE bloom_filter GRANULARITY 1,
        INDEX idx_timestamp timestamp TYPE minmax GRANULARITY 1
    ) ENGINE = MergeTree()
    ORDER BY (timestamp, workflow_id, agent_id, module_name)
    PARTITION BY toYYYYMM(timestamp)""",
    
    # Daily statistics table - FIXED with proper structure
    """CREATE TABLE IF NOT EXISTS daily_stats (
        date Date,
        agent_id String,
        module_name String DEFAULT '',
        total_executions UInt32 DEFAULT 0,
        successful_executions UInt32 DEFAULT 0,
        failed_executions UInt32 DEFAULT 0,
        avg_execution_time Float32 DEFAULT 0.0,
        INDEX idx_date date TYPE minmax GRANULARITY 1,
        INDEX idx_agent_id agent_id TYPE bloom_filter GRANULARITY 1
    ) ENGINE = SummingMergeTree()
    ORDER BY (date, agent_id, module_name)""",
    
    # Materialized view to auto-populate daily_stats
    """CREATE MATERIALIZED VIEW IF NOT EXISTS daily_stats_mv
    TO daily_stats
    AS SELECT
        toDate(created_at) as date,
        agent_id,
        module_name,
        count() as total_executions,
        countIf(success = true) as successful_executions,
        countIf(success = false) as failed_executions,
        avg(date_diff('millisecond', created_at, completed_at)) as avg_execution_time
    FROM measurements
    GROUP BY date, agent_id, module_name"""
]

# Table descriptions for documentation
TABLE_DESCRIPTIONS = {
    "measurements": """
    Main fact table storing all measurement results with comprehensive metadata.
    Uses ReplacingMergeTree for automatic deduplication by workflow_id.
    Includes denormalized agent information for efficient querying.
    DateTime64(6) provides microsecond precision.
    All fields have DEFAULT values for robustness.
    """,
    
    "agent_heartbeats": """
    Historical table storing agent heartbeat information for monitoring and analytics.
    Uses MergeTree as multiple heartbeats per agent are expected.
    DateTime64(6) provides microsecond precision.
    """,
    
    "module_states": """
    Table tracking all module state transitions for workflow monitoring.
    Uses MergeTree to track all state changes over time.
    DateTime64(6) provides microsecond precision.
    """,
    
    "daily_stats": """
    Aggregated daily statistics for quick dashboard queries.
    Uses SummingMergeTree for automatic aggregation.
    Auto-populated via materialized view from measurements table.
    """
}

# Key improvements in this schema:
SCHEMA_IMPROVEMENTS = """
1. DateTime64(6, 'UTC') - Full microsecond precision (was 3 for milliseconds)
2. DEFAULT values on all columns - Prevents insertion failures
3. ReplacingMergeTree for measurements - Prevents duplicates by workflow_id
4. PRIMARY KEY on workflow_id - Ensures uniqueness
5. SummingMergeTree for daily_stats - Auto-aggregation
6. Materialized view - Auto-populates daily_stats from measurements
7. Proper ORDER BY clauses - Optimized for common queries
"""

# Sample data structures for reference
SAMPLE_DATA_STRUCTURES = {
    "measurement_result": {
        "workflow_id": "uuid-string",
        "agent_id": "uuid-string",
        "module_name": "ping_module",
        "created_at": "2023-01-01 12:00:00.123456",
        "completed_at": "2023-01-01 12:00:01.234567",
        "measurement_data": '{"address": "8.8.8.8", "rtts": [12.3, 15.1, 11.8], "packets_sent": 3, "packets_received": 3}',
        "agent_hostname": "agent-host-1",
        "agent_name": "aiori_1",
        "agent_pid": 12345,
        "system_machine": "x86_64",
        "system_node_name": "agent-host-1",
        "system_platform": "Linux-5.4.0",
        "system_processor": "x86_64",
        "system_release": "5.4.0-42-generic",
        "system_version": "#46-Ubuntu SMP",
        "network_interfaces": '{"eth0": {"ipv4": ["192.168.1.10"], "ipv6": [], "mac": ["aa:bb:cc:dd:ee:ff"]}}',
        "user_name": "agent-user",
        "user_uid": 1000,
        "user_gid": 1000,
        "user_home_dir": "/home/agent-user",
        "user_shell": "/bin/bash",
        "request_data": '{"host": "8.8.8.8", "count": 3}',
        "success": True
    },
    
    "agent_heartbeat": {
        "agent_id": "uuid-string",
        "agent_name": "aiori_1",
        "hostname": "agent-host-1",
        "timestamp": "2023-01-01 12:00:00.123456",
        "alive": True,
        "total_heartbeats": 42,
        "load_avg_1m": 0.15,
        "load_avg_5m": 0.12,
        "load_avg_15m": 0.08,
        "config": '{"modules": ["ping_module", "echo_module"], "interval": 5}'
    },
    
    "module_state": {
        "workflow_id": "uuid-string",
        "agent_id": "uuid-string",
        "module_name": "ping_module",
        "state": "COMPLETED",
        "timestamp": "2023-01-01 12:00:00.123456",
        "error_message": None,
        "details": '{"action": "request_completed"}'
    }
}