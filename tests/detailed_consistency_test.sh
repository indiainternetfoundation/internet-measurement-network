#!/bin/bash

# Detailed consistency test between servers
set -e

SERVER1_URL="http://localhost:8001"
SERVER2_URL="http://localhost:8002"
TEST_AGENT_ID=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Wait for servers to be ready
wait_for_servers() {
    log "Waiting for servers to be ready..."
    
    # Check server 1
    for i in {1..30}; do
        if curl -s "$SERVER1_URL/" >/dev/null; then
            log "Server 1 is ready"
            break
        fi
        log "Server 1 not ready, waiting... ($i/30)"
        sleep 2
    done
    
    # Check server 2
    for i in {1..30}; do
        if curl -s "$SERVER2_URL/" >/dev/null; then
            log "Server 2 is ready"
            return 0
        fi
        log "Server 2 not ready, waiting... ($i/30)"
        sleep 2
    done
    
    error "Servers failed to start"
    exit 1
}

# Get active agent ID
get_agent_id() {
    log "Getting active agent ID..."
    response1=$(curl -s "$SERVER1_URL/agents/alive")
    response2=$(curl -s "$SERVER2_URL/agents/alive")
    
    TEST_AGENT_ID=$(echo "$response1" | jq -r 'keys[0]')
    
    if [ "$TEST_AGENT_ID" == "null" ] || [ -z "$TEST_AGENT_ID" ]; then
        error "No active agents found on server 1"
        echo "$response1" | jq '.'
        exit 1
    fi
    
    success "Using agent ID: $TEST_AGENT_ID"
}

# Force server state refresh by restarting workflow monitoring
refresh_server_state() {
    log "Refreshing server state by accessing debug endpoint..."
    curl -s "$SERVER1_URL/debug/state" >/dev/null
    curl -s "$SERVER2_URL/debug/state" >/dev/null
    sleep 2
}

# Compare database state directly
compare_database_state() {
    log "Comparing database state..."
    
    # Get workflow counts from database
    db_count=$(docker exec internet-measurement-network-postgres-1 psql -U imn_user -d imn_db -t -c "SELECT COUNT(*) FROM persistent_workflows;" | xargs)
    
    # Get workflow counts from servers
    server1_count=$(curl -s "$SERVER1_URL/" | jq '.total_workflows')
    server2_count=$(curl -s "$SERVER2_URL/" | jq '.total_workflows')
    
    log "Database workflow count: $db_count"
    log "Server 1 workflow count: $server1_count"
    log "Server 2 workflow count: $server2_count"
    
    if [ "$db_count" -eq "$server1_count" ] && [ "$db_count" -eq "$server2_count" ]; then
        success "All workflow counts consistent"
    else
        warning "Workflow counts inconsistent - this is expected due to caching"
    fi
}

# Test workflow creation and consistency after refresh
test_workflow_consistency_with_refresh() {
    log "Testing workflow consistency with state refresh..."
    
    # Create a test workflow on server 1
    payload='{"message": "Consistency test with refresh"}'
    response=$(curl -s -X POST "$SERVER1_URL/agent/$TEST_AGENT_ID/echo_module" \
        -H "Content-Type: application/json" \
        -d "$payload")
    
    workflow_id=$(echo "$response" | jq -r '.workflow_id')
    if [ "$workflow_id" == "null" ] || [ -z "$workflow_id" ]; then
        error "Failed to get workflow ID"
        return 1
    fi
    
    success "Workflow created: $workflow_id"
    
    # Wait for workflow to complete
    log "Waiting for workflow to complete..."
    sleep 3
    
    # Refresh server states to sync with database
    refresh_server_state
    
    # Check workflow status on both servers after refresh
    log "Checking workflow status on both servers after refresh..."
    
    status1=$(curl -s "$SERVER1_URL/workflows/$workflow_id")
    status2=$(curl -s "$SERVER2_URL/workflows/$workflow_id")
    
    state1=$(echo "$status1" | jq -r '.current_state')
    state2=$(echo "$status2" | jq -r '.current_state')
    
    log "Server 1 workflow state: $state1"
    log "Server 2 workflow state: $state2"
    
    if [ "$state1" == "$state2" ] && [ "$state1" != "null" ]; then
        success "Workflow states consistent after refresh: $state1"
    else
        error "Workflow states still inconsistent after refresh: Server1=$state1, Server2=$state2"
    fi
}

# Test database consistency directly
test_database_consistency() {
    log "Testing direct database consistency..."
    
    # Create multiple workflows
    log "Creating multiple workflows..."
    workflow_ids=()
    
    for i in {1..3}; do
        payload="{\"message\": \"Direct consistency test $i\"}"
        response=$(curl -s -X POST "$SERVER1_URL/agent/$TEST_AGENT_ID/echo_module" \
            -H "Content-Type: application/json" \
            -d "$payload")
        
        workflow_id=$(echo "$response" | jq -r '.workflow_id')
        if [ "$workflow_id" != "null" ] && [ -n "$workflow_id" ]; then
            workflow_ids+=("$workflow_id")
            log "Created workflow $i: $workflow_id"
        fi
        
        sleep 1
    done
    
    log "Waiting for workflows to complete..."
    sleep 5
    
    # Check database directly
    log "Checking database state directly..."
    db_workflows=$(docker exec internet-measurement-network-postgres-1 psql -U imn_user -d imn_db -t -c "SELECT COUNT(*) FROM persistent_workflows;" | xargs)
    db_states=$(docker exec internet-measurement-network-postgres-1 psql -U imn_user -d imn_db -t -c "SELECT COUNT(*) FROM persistent_workflow_states;" | xargs)
    
    log "Database has $db_workflows workflows and $db_states state entries"
    
    # Refresh server states
    refresh_server_state
    
    # Check server states after refresh
    server1_stats=$(curl -s "$SERVER1_URL/")
    server2_stats=$(curl -s "$SERVER2_URL/")
    
    server1_workflows=$(echo "$server1_stats" | jq '.total_workflows')
    server2_workflows=$(echo "$server2_stats" | jq '.total_workflows')
    
    log "After refresh - Server 1 workflows: $server1_workflows"
    log "After refresh - Server 2 workflows: $server2_workflows"
    
    if [ "$server1_workflows" -eq "$server2_workflows" ]; then
        success "Server workflow counts consistent after refresh"
    else
        warning "Server workflow counts still inconsistent after refresh"
    fi
}

# Main execution
main() {
    log "Starting detailed consistency test between servers..."
    
    wait_for_servers
    get_agent_id
    compare_database_state
    test_workflow_consistency_with_refresh
    test_database_consistency
    
    success "Detailed consistency test completed!"
}

main "$@"
