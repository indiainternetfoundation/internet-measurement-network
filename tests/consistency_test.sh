#!/bin/bash

# Test consistency of workflow data between two servers
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

# Compare server states
compare_server_states() {
    log "Comparing server states..."
    
    # Get basic stats from both servers
    stats1=$(curl -s "$SERVER1_URL/")
    stats2=$(curl -s "$SERVER2_URL/")
    
    log "Server 1 stats:"
    echo "$stats1" | jq '.'
    
    log "Server 2 stats:"
    echo "$stats2" | jq '.'
    
    # Compare agent counts
    agents1=$(echo "$stats1" | jq '.total_agents')
    agents2=$(echo "$stats2" | jq '.total_agents')
    
    if [ "$agents1" -eq "$agents2" ]; then
        success "Agent counts match: $agents1"
    else
        warning "Agent counts differ: Server1=$agents1, Server2=$agents2"
    fi
    
    # Compare alive agent counts
    alive1=$(echo "$stats1" | jq '.alive_agents')
    alive2=$(echo "$stats2" | jq '.alive_agents')
    
    if [ "$alive1" -eq "$alive2" ]; then
        success "Alive agent counts match: $alive1"
    else
        warning "Alive agent counts differ: Server1=$alive1, Server2=$alive2"
    fi
    
    # Compare workflow counts
    workflows1=$(echo "$stats1" | jq '.total_workflows')
    workflows2=$(echo "$stats2" | jq '.total_workflows')
    
    if [ "$workflows1" -eq "$workflows2" ]; then
        success "Workflow counts match: $workflows1"
    else
        warning "Workflow counts differ: Server1=$workflows1, Server2=$workflows2"
    fi
}

# Test workflow creation and consistency
test_workflow_consistency() {
    log "Testing workflow consistency between servers..."
    
    # Create a test workflow
    payload='{"message": "Consistency test message"}'
    response=$(curl -s -X POST "$SERVER1_URL/agent/$TEST_AGENT_ID/echo_module" \
        -H "Content-Type: application/json" \
        -d "$payload")
    
    echo "$response" | jq '.'
    
    workflow_id=$(echo "$response" | jq -r '.workflow_id')
    if [ "$workflow_id" == "null" ] || [ -z "$workflow_id" ]; then
        error "Failed to get workflow ID"
        return 1
    fi
    
    success "Workflow created: $workflow_id"
    
    # Wait for workflow to complete
    log "Waiting for workflow to complete..."
    sleep 3
    
    # Check workflow status on both servers
    log "Checking workflow status on both servers..."
    
    status1=$(curl -s "$SERVER1_URL/workflows/$workflow_id")
    status2=$(curl -s "$SERVER2_URL/workflows/$workflow_id")
    
    state1=$(echo "$status1" | jq -r '.current_state')
    state2=$(echo "$status2" | jq -r '.current_state')
    
    log "Server 1 workflow state: $state1"
    log "Server 2 workflow state: $state2"
    
    if [ "$state1" == "$state2" ]; then
        success "Workflow states consistent: $state1"
    else
        error "Workflow states inconsistent: Server1=$state1, Server2=$state2"
    fi
    
    # Compare full workflow details
    log "Comparing full workflow details..."
    echo "Server 1 details:"
    echo "$status1" | jq '.'
    echo "Server 2 details:"
    echo "$status2" | jq '.'
}

# List workflows on both servers
list_workflows_comparison() {
    log "Comparing workflow lists..."
    
    workflows1=$(curl -s "$SERVER1_URL/workflows")
    workflows2=$(curl -s "$SERVER2_URL/workflows")
    
    count1=$(echo "$workflows1" | jq '.total')
    count2=$(echo "$workflows2" | jq '.total')
    
    log "Server 1 workflow count: $count1"
    log "Server 2 workflow count: $count2"
    
    if [ "$count1" -eq "$count2" ]; then
        success "Workflow counts match"
    else
        warning "Workflow counts differ"
    fi
    
    log "Server 1 workflows:"
    echo "$workflows1" | jq '.workflows[] | {workflow_id, current_state}' 2>/dev/null || echo "None"
    
    log "Server 2 workflows:"
    echo "$workflows2" | jq '.workflows[] | {workflow_id, current_state}' 2>/dev/null || echo "None"
}

# Main execution
main() {
    log "Starting consistency test between servers..."
    
    wait_for_servers
    get_agent_id
    compare_server_states
    test_workflow_consistency
    list_workflows_comparison
    
    success "Consistency test completed!"
}

main "$@"
