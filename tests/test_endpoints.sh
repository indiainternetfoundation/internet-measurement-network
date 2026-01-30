#!/bin/bash

# Comprehensive API Endpoint Testing Script
# Tests basic functionality and prepares for chaos testing

set -e  # Exit on any error

BASE_URL="http://localhost:8000"
TEST_AGENT_ID=""
WORKFLOW_IDS=()

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

# Wait for server to be ready
wait_for_server() {
    log "Waiting for server to be ready..."
    for i in {1..30}; do
        if curl -s "$BASE_URL/" >/dev/null; then
            success "Server is ready"
            return 0
        fi
        log "Server not ready, waiting... ($i/30)"
        sleep 2
    done
    error "Server failed to start"
    exit 1
}

# Get active agent ID
get_agent_id() {
    log "Getting active agent ID..."
    response=$(curl -s "$BASE_URL/agents/alive")
    TEST_AGENT_ID=$(echo "$response" | jq -r 'keys[0]')
    
    if [ "$TEST_AGENT_ID" == "null" ] || [ -z "$TEST_AGENT_ID" ]; then
        error "No active agents found"
        echo "$response" | jq '.'
        exit 1
    fi
    
    success "Using agent ID: $TEST_AGENT_ID"
    echo "$response" | jq --arg id "$TEST_AGENT_ID" '.[$id]'
}

# Test health endpoints
test_health_endpoints() {
    log "Testing health endpoints..."
    
    # Root endpoint
    log "Testing root endpoint..."
    response=$(curl -sf "$BASE_URL/")
    echo "$response" | jq '.'
    
    if [ "$(echo "$response" | jq -r '.status')" != "ok" ]; then
        error "Root endpoint failed"
        return 1
    fi
    
    # Agents endpoints
    log "Testing agents endpoints..."
    curl -sf "$BASE_URL/agents" | jq '.' > /dev/null
    curl -sf "$BASE_URL/agents/alive" | jq '.' > /dev/null
    curl -sf "$BASE_URL/agents/dead" | jq '.' > /dev/null
    curl -sf "$BASE_URL/agents/$TEST_AGENT_ID" | jq '.' > /dev/null
    
    success "Health endpoints working"
}

# Test echo module
test_echo_module() {
    log "Testing echo module..."
    
    # Send echo request
    payload='{"message": "Hello, World! Testing echo module."}'
    response=$(curl -s -X POST "$BASE_URL/agent/$TEST_AGENT_ID/echo_module" \
        -H "Content-Type: application/json" \
        -d "$payload")
    
    echo "$response" | jq '.'
    
    workflow_id=$(echo "$response" | jq -r '.workflow_id')
    if [ "$workflow_id" == "null" ] || [ -z "$workflow_id" ]; then
        error "Failed to get workflow ID from echo module"
        return 1
    fi
    
    WORKFLOW_IDS+=("$workflow_id")
    success "Echo module workflow initiated: $workflow_id"
    
    # Wait for completion
    log "Waiting for echo workflow to complete..."
    sleep 2
    
    # Check workflow status
    status_response=$(curl -s "$BASE_URL/workflows/$workflow_id")
    current_state=$(echo "$status_response" | jq -r '.current_state')
    
    if [ "$current_state" == "COMPLETED" ]; then
        success "Echo workflow completed successfully"
        echo "$status_response" | jq '.'
    else
        warning "Echo workflow state: $current_state"
        echo "$status_response" | jq '.'
    fi
}

# Test ping module
test_ping_module() {
    log "Testing ping module..."
    
    # Test with Google DNS
    payload='{"host": "8.8.8.8", "count": 3}'
    response=$(curl -s -X POST "$BASE_URL/agent/$TEST_AGENT_ID/ping_module" \
        -H "Content-Type: application/json" \
        -d "$payload")
    
    echo "$response" | jq '.'
    
    workflow_id=$(echo "$response" | jq -r '.workflow_id')
    if [ "$workflow_id" == "null" ] || [ -z "$workflow_id" ]; then
        error "Failed to get workflow ID from ping module"
        return 1
    fi
    
    WORKFLOW_IDS+=("$workflow_id")
    success "Ping module workflow initiated: $workflow_id"
    
    # Wait for completion
    log "Waiting for ping workflow to complete..."
    sleep 3
    
    # Check workflow status
    status_response=$(curl -s "$BASE_URL/workflows/$workflow_id")
    current_state=$(echo "$status_response" | jq -r '.current_state')
    
    if [ "$current_state" == "COMPLETED" ]; then
        success "Ping workflow completed successfully"
        echo "$status_response" | jq '.'
    else
        warning "Ping workflow state: $current_state"
        echo "$status_response" | jq '.'
    fi
}

# Test faulty module
test_faulty_module() {
    log "Testing faulty module (intentional failure)..."
    
    # Send faulty request with crash
    payload='{"message": "Test message", "crash": true}'
    response=$(curl -s -X POST "$BASE_URL/agent/$TEST_AGENT_ID/faulty_module" \
        -H "Content-Type: application/json" \
        -d "$payload")
    
    echo "$response" | jq '.'
    
    workflow_id=$(echo "$response" | jq -r '.workflow_id')
    if [ "$workflow_id" == "null" ] || [ -z "$workflow_id" ]; then
        error "Failed to get workflow ID from faulty module"
        return 1
    fi
    
    WORKFLOW_IDS+=("$workflow_id")
    success "Faulty module workflow initiated: $workflow_id"
    
    # Wait for completion
    log "Waiting for faulty workflow to complete (should fail)..."
    sleep 2
    
    # Check workflow status
    status_response=$(curl -s "$BASE_URL/workflows/$workflow_id")
    current_state=$(echo "$status_response" | jq -r '.current_state')
    
    if [ "$current_state" == "FAILED" ]; then
        success "Faulty workflow failed as expected"
        echo "$status_response" | jq '.'
    else
        warning "Faulty workflow state: $current_state (expected FAILED)"
        echo "$status_response" | jq '.'
    fi
}

# Test workflow management endpoints
test_workflow_endpoints() {
    log "Testing workflow management endpoints..."
    
    # List all workflows
    log "Listing all workflows..."
    curl -s "$BASE_URL/workflows" | jq '.'
    
    # List completed workflows
    log "Listing completed workflows..."
    curl -s "$BASE_URL/workflows?status=COMPLETED" | jq '.'
    
    # List failed workflows
    log "Listing failed workflows..."
    curl -s "$BASE_URL/workflows?status=FAILED" | jq '.'
    
    # Test invalid status filter
    log "Testing invalid status filter..."
    curl -s "$BASE_URL/workflows?status=INVALID" | jq '.'
    
    success "Workflow management endpoints working"
}

# Test debug endpoints
test_debug_endpoints() {
    log "Testing debug endpoints..."
    
    # Debug state
    log "Checking debug state..."
    debug_response=$(curl -sf "$BASE_URL/debug/state")
    echo "$debug_response" | jq '.'
    
    # Verify agent is alive
    agent_count=$(echo "$debug_response" | jq '.agents.alive')
    if [[ "$agent_count" =~ ^[0-9]+$ ]] && [ "$agent_count" -gt 0 ]; then
        success "Agent is alive"
    else
        warning "No alive agents detected"
    fi
    
    success "Debug endpoints working"
}

# Test async execution
test_async_execution() {
    log "Testing async execution..."
    
    # Send async echo request
    payload='{"message": "Async test message"}'
    response=$(curl -s -X POST "$BASE_URL/agent/$TEST_AGENT_ID/echo_module/async" \
        -H "Content-Type: application/json" \
        -d "$payload")
    
    echo "$response" | jq '.'
    
    workflow_id=$(echo "$response" | jq -r '.workflow_id')
    if [ "$workflow_id" == "null" ] || [ -z "$workflow_id" ]; then
        error "Failed to get workflow ID from async execution"
        return 1
    fi
    
    WORKFLOW_IDS+=("$workflow_id")
    success "Async workflow initiated: $workflow_id"
    
    # Wait and check status
    sleep 2
    status_response=$(curl -s "$BASE_URL/workflows/$workflow_id")
    echo "$status_response" | jq '.'
}

# Test workflow cancellation
test_workflow_cancellation() {
    log "Testing workflow cancellation..."
    
    # Start a new ping workflow that we'll cancel
    payload='{"host": "1.1.1.1", "count": 10}'
    response=$(curl -s -X POST "$BASE_URL/agent/$TEST_AGENT_ID/ping_module" \
        -H "Content-Type: application/json" \
        -d "$payload")
    
    workflow_id=$(echo "$response" | jq -r '.workflow_id')
    if [ "$workflow_id" == "null" ] || [ -z "$workflow_id" ]; then
        error "Failed to get workflow ID for cancellation test"
        return 1
    fi
    
    success "Workflow to cancel: $workflow_id"
    
    # Give it a moment to start
    sleep 1
    
    # Cancel the workflow
    cancel_response=$(curl -s -X POST "$BASE_URL/workflows/$workflow_id/cancel" \
        -H "Content-Type: application/json")
    
    echo "$cancel_response" | jq '.'
    
    # Check that it was cancelled
    status_response=$(curl -s "$BASE_URL/workflows/$workflow_id")
    current_state=$(echo "$status_response" | jq -r '.current_state')
    
    if [ "$current_state" == "FAILED" ]; then
        success "Workflow cancelled successfully"
    else
        warning "Workflow cancellation result: $current_state"
    fi
}

# Summary report
print_summary() {
    log "=== TEST SUMMARY ==="
    log "Agent ID used: $TEST_AGENT_ID"
    log "Workflows tested: ${#WORKFLOW_IDS[@]}"
    
    for workflow_id in "${WORKFLOW_IDS[@]}"; do
        status_response=$(curl -s "$BASE_URL/workflows/$workflow_id")
        current_state=$(echo "$status_response" | jq -r '.current_state')
        module_name=$(echo "$status_response" | jq -r '.module_name')
        log "Workflow $workflow_id ($module_name): $current_state"
    done
    
    log "Debug state:"
    curl -s "$BASE_URL/debug/state" | jq '.workflows.states'
}

# Main execution
main() {
    log "Starting comprehensive API endpoint testing..."
    
    wait_for_server
    get_agent_id
    test_health_endpoints
    test_echo_module
    test_ping_module
    test_faulty_module
    test_workflow_endpoints
    test_debug_endpoints
    test_async_execution
    test_workflow_cancellation
    print_summary
    
    success "All basic tests completed!"
    log "Ready for chaos testing phase."
}

# Run main function
main "$@"