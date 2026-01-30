# Internet Measurement Network (IMN)

A distributed system for performing network measurements using autonomous agents with real-time coordination, monitoring, and analytics capabilities.

## 🏗️ Architecture Overview

The Internet Measurement Network is a microservices-based system that enables distributed network measurement tasks through autonomous agents. The architecture leverages NATS for messaging, PostgreSQL for system data, ClickHouse for analytics, and follows a modular design for extensibility.

### Core Components

#### 1. Agents (`src/aiori_agent/`)
Autonomous measurement nodes that dynamically load modules to perform various network tests:
- Dynamic module loading with hot-reloading capabilities
- NATS integration for communication
- Heartbeat mechanism for health monitoring
- Crash recovery and error handling mechanisms
- Support for multiple measurement modules

#### 2. Server (`server/`)
Central coordination service built with FastAPI that:
- Maintains registry of active agents
- Processes agent heartbeats
- Provides REST API for querying agent status
- Routes measurement requests to appropriate agents
- Validates measurement requests against module schemas
- Tracks workflow execution states
- Stores results in ClickHouse analytics database

#### 3. NATS Messaging System
Message broker serving as the communication backbone:
- Pub/sub messaging for all components
- Agent-to-server and server-to-agent communication
- Health monitoring through heartbeat messages
- Scalable, decoupled architecture

#### 4. Data Storage & Analytics
- **PostgreSQL**: System database for agent registry and workflow tracking
- **ClickHouse**: Analytics database for measurement results with high-performance queries
- **ReplacingMergeTree engine**: Automatic deduplication of measurement data

#### 5. Observability Stack (Optional)
Full OpenTelemetry observability pipeline:
- **OpenTelemetry Collector**: Aggregates traces, logs, and metrics
- **OpenSearch**: Storage engine for telemetry data
- **Data Prepper**: Processes and transforms observability data
- **OpenSearch Dashboards**: Visualization interface

## 🔄 Data Flow

1. **Agent Registration**:
   - Agents send heartbeats to `agent.heartbeat_module` subject
   - Server maintains agent registry and health status in PostgreSQL

2. **Measurement Request**:
   - Client sends request to server API endpoint `/agent/{agent_id}/{module_name}`
   - Server validates request against module schema
   - Server publishes request to appropriate NATS subject

3. **Measurement Execution**:
   - Agent receives request on its input subject
   - Agent executes measurement using loaded module
   - Module performs network test (ping, echo, etc.)

4. **Result Reporting**:
   - Agent publishes results to output subject
   - Agent reports state transitions to `agent.module.state`
   - Server captures workflow results and stores them in ClickHouse

5. **Analytics Pipeline**:
   - Measurement results stored in ClickHouse `measurements` table
   - Agent heartbeats stored in `agent_heartbeats` table
   - Module state transitions stored in `module_states` table
   - Daily statistics aggregated via materialized view

## 🐳 Deployment

### Prerequisites
- Docker and Docker Compose
- Python 3.10+ (for local development)

### Quick Start

#### Core System (Current)
1. **Start the core system**:
   ```bash
   docker-compose -f core-pipeline.yml up --build
   ```

2. **Access services**:
   - **Server API**: `localhost:8001` (server1), `localhost:8002` (server2)
   - **NATS Server**: `localhost:4222`
   - **ClickHouse**: `localhost:8123` (HTTP), `localhost:9000` (Native)
   - **PostgreSQL**: `localhost:5432`

#### Full Observability Stack (Optional)
1. **Start with full observability**:
   ```bash
   docker-compose -f docker/docker-compose.yml up --build
   ```

2. **Additional services**:
   - **OpenSearch**: `localhost:9200`
   - **OpenSearch Dashboards**: `localhost:5601`
   - **OpenTelemetry Collector**: `localhost:4317`

### Individual Component Startup

#### Server
```bash
python3 -m server.main
```

#### Agent
```bash
python3 -m aiori_agent --nats_url nats://localhost:4222 \
  --agent_id $(uuidgen) \
  --modules_path ./modules/
```

## 🛠️ API Usage

### Health & Discovery
```bash
# Check system health
curl http://localhost:8000/

# List all agents
curl http://localhost:8000/agents

# List alive agents
curl http://localhost:8000/agents/alive

# Get specific agent info
curl http://localhost:8000/agents/{agent_id}
```

### Module Execution
```bash
# Execute echo module
curl -X POST http://localhost:8000/agent/{agent_id}/echo_module \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, World!"}'

# Execute ping module
curl -X POST http://localhost:8000/agent/{agent_id}/ping_module \
  -H "Content-Type: application/json" \
  -d '{"host": "8.8.8.8", "count": 4}'

# Execute faulty module (testing errors)
curl -X POST http://localhost:8000/agent/{agent_id}/faulty_module \
  -H "Content-Type: application/json" \
  -d '{"message": "test", "crash": true}'

# Async execution
curl -X POST http://localhost:8000/agent/{agent_id}/echo_module/async \
  -H "Content-Type: application/json" \
  -d '{"message": "async test"}'
```

### Workflow Management
```bash
# List all workflows
curl http://localhost:8000/workflows

# List workflows by status
curl http://localhost:8000/workflows?status=COMPLETED
curl http://localhost:8000/workflows?status=FAILED

# Get workflow details
curl http://localhost:8000/workflows/{workflow_id}

# Cancel workflow
curl -X POST http://localhost:8000/workflows/{workflow_id}/cancel
```

### Debug Endpoints
```bash
# System state overview
curl http://localhost:8000/debug/state
```

## 📊 Module Specifications

### Echo Module
Simple module that echoes back received messages with processing timestamp.

**Schema**:
```json
{
  "message": "string"
}
```

**Subjects**:
- Input: `agent.{agent_id}.working_module.in`
- Output: `agent.{agent_id}.working_module.out`
- Error: `agent.{agent_id}.working_module.error`

### Ping Module
Performs ICMP ping or TCP ping to target hosts.

**Schema**:
```json
{
  "host": "IP/Hostname",
  "count": 3,
  "port": 80
}
```

**Subjects**:
- Input: `agent.{agent_id}.in`
- Output: `agent.{agent_id}.out`
- Error: `agent.{agent_id}.error`

### Faulty Module
Test module for simulating errors and delays.

**Schema**:
```json
{
  "message": "string",
  "delay": null,
  "crash": false
}
```

**Subjects**:
- Input: `agent.{agent_id}.faulty_module.in`
- Output: `agent.{agent_id}.faulty_module.out`
- Error: `agent.{agent_id}.faulty_module.error`

## 🧪 Testing

### Automated Testing
```bash
# Run comprehensive endpoint tests
./tests/test_endpoints.sh

# Run specific tests
curl -X POST http://localhost:8000/agent/{agent_id}/echo_module \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}'
```

### Manual Verification
1. Start the system with `docker-compose -f core-pipeline.yml up`
2. Get an active agent ID:
   ```bash
   curl -s http://localhost:8001/agents/alive | jq 'keys[0]'
   ```
3. Test module execution with the retrieved agent ID
4. Monitor workflow states and results

## 📊 Analytics & Monitoring

### Data Storage
- **ClickHouse Tables**:
  - `measurements`: Main measurement results with comprehensive metadata
  - `agent_heartbeats`: Agent health monitoring data
  - `module_states`: Workflow state transitions
  - `daily_stats`: Aggregated daily statistics (auto-populated)

### Query Examples
```sql
-- Get measurement results for a workflow
SELECT * FROM measurements WHERE workflow_id = 'your-workflow-id'

-- Check agent heartbeats
SELECT agent_id, agent_name, timestamp, alive FROM agent_heartbeats ORDER BY timestamp DESC LIMIT 10

-- Get daily statistics
SELECT date, agent_id, module_name, total_executions, successful_executions FROM daily_stats
```

### Monitoring Endpoints
- **NATS Monitoring**: `localhost:8222`
- **ClickHouse HTTP Interface**: `localhost:8123`
- **PostgreSQL**: `localhost:5432`

### Observability (Optional)
- **OpenSearch Dashboards**: `localhost:5601` (visualization)
- **OpenTelemetry Collector**: `localhost:4317` (telemetry collection)
- **Data Prepper**: `localhost:21891-21893` (data processing)

## 🚀 Development

### Project Structure
```
├── docker/              # Docker configurations
├── modules/             # Agent modules (ping, echo, faulty, heartbeat)
├── otlp/                # OpenTelemetry collector config
├── server/              # FastAPI server implementation
├── src/aiori_agent/     # Agent core implementation
├── tests/               # Test scripts
└── core-pipeline.yml    # Main system orchestration
```

### Adding New Modules
1. Create new module in `modules/` directory
2. Extend `BaseWorker` class
3. Implement required methods (`setup`, `run`, `handle`)
4. Define input schema using Pydantic
5. Set appropriate subject names

### Extending Server Functionality
1. Add new endpoints in `server/main.py`
2. Follow existing patterns for validation and error handling
3. Maintain consistent workflow state management

## 🔧 Configuration

### Environment Variables
```bash
# NATS configuration
NATS_URL=nats://localhost:4222

# Database
DBOS_SYSTEM_DATABASE_URL=postgresql://your_db_user:your_db_password@localhost:5432/your_database

# ClickHouse
CLICKHOUSE_HOST=clickhouse
CLICKHOUSE_PORT=8123
CLICKHOUSE_DATABASE=imn
CLICKHOUSE_USERNAME=your_clickhouse_user

# OpenTelemetry (Optional)
OTLP_TRACE_ENDPOINT=otel-collector:4317
OTLP_METRICS_ENDPOINT=otel-collector:4317
OTLP_LOGS_ENDPOINT=otel-collector:4317
```

### Module Subject Patterns
Each module defines its own subject naming pattern:
- Echo Module: `agent.{agent_id}.working_module.{in|out|error}`
- Faulty Module: `agent.{agent_id}.faulty_module.{in|out|error}`
- Ping Module: `agent.{agent_id}.{in|out|error}`

## 📊 Key Features

1. **Distributed Architecture**: Scalable agent-based measurement system
2. **Real-time Coordination**: Instantaneous command and control
3. **Workflow Tracking**: Detailed state management for all operations
4. **High-Performance Analytics**: ClickHouse for fast querying of measurement data
5. **Extensible Design**: Easy addition of new measurement modules
6. **Robust Data Storage**: PostgreSQL for system data, ClickHouse for analytics
7. **Error Handling**: Robust error detection and reporting

## 📋 Current Status

The system is fully operational with:
- Multiple server instances running
- Multiple agent instances actively monitoring
- ClickHouse storing measurement results with automatic deduplication
- PostgreSQL maintaining agent registry and workflow states

**Note**: Currently running core system only. Full observability stack (OpenSearch, OpenTelemetry) is available but not active.

## 📋 Future Enhancements

1. **Advanced Analytics**: ML-based anomaly detection on measurement data
2. **Dashboard Integration**: Custom visualization for measurement analytics
3. **Security Enhancements**: Authentication and encryption
4. **Multi-region Support**: Geographically distributed agents
5. **Performance Optimization**: Query optimization and indexing strategies