#!/bin/bash

# Chaos Testing Script for Internet Measurement Network
# Tests system durability under various failure scenarios

set -e  # Exit on any error

BASE_URL="http://localhost:8000"
TEST_AGENT_ID=""
FAILED_TESTS=0
PASSED_TESTS=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
    ((PASSED_TESTS++))
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    ((FAILED_TESTS++))
}

critical() {
    echo -e "${PURPLE}[CRITICAL]${NC} $1"
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
}

# Test 1: High Volume Request Flood
test_request_flood() {
    log "=== Test 1: High Volume Request Flood ==="
    
    local num_requests=50
    local completed=0
    local failed=0
    
    log "Sending $num_requests rapid requests..."
    
    # Send requests in parallel
    for i in $(seq 1 $num_requests); do
        {
            payload="{\"message\": \"Flood test message $i\"}"
            response=$(curl -s -X POST "$BASE_URL/agent/$TEST_AGENT_ID/echo_module" \
                -H "Content-Type: application/json" \
                -d "$payload" -w "%{http_code}" -o /dev/null)
            
            if [ "$response" == "200" ]; then
                ((completed++))
            else
                ((failed++))
            fi
        } &
        
        # Limit concurrency to prevent overwhelming the system
        if [ $((i % 10)) -eq 0 ]; then
            wait
        fi
    done
    
    # Wait for all background jobs
    wait
    
    log "Results: $completed successful, $failed failed"
    
    if [ $failed -eq 0 ]; then
        success "Request flood test passed"
    else
        error "Request flood test failed: $failed requests failed"
    fi
}

# Test 2: Concurrent Module Execution
test_concurrent_modules() {
    log "=== Test 2: Concurrent Module Execution ==="
    
    local workflows=()
    
    # Start multiple different modules simultaneously
    log "Starting concurrent echo module..."
    payload='{"message": "Concurrent echo test"}'
    response=$(curl -s -X POST "$BASE_URL/agent/$TEST_AGENT_ID/echo_module" \
        -H "Content-Type: application/json" \
        -d "$payload")
    workflows+=($(echo "$response" | jq -r '.workflow_id'))
    
    log "Starting concurrent ping module..."
    payload='{"host": "8.8.8.8", "count": 2}'
    response=$(curl -s -X POST "$BASE_URL/agent/$TEST_AGENT_ID/ping_module" \
        -H "Content-Type: application/json" \
        -d "$payload")
    workflows+=($(echo "$response" | jq -r '.workflow_id'))
    
    log "Starting concurrent faulty module (should fail)..."
    payload='{"message": "Concurrent fault test", "delay": 1}'
    response=$(curl -s -X POST "$BASE_URL/agent/$TEST_AGENT_ID/faulty_module" \
        -H "Content-Type: application/json" \
        -d "$payload")
    workflows+=($(echo "$response" | jq -r '.workflow_id'))
    
    # Wait for completion
    log "Waiting for concurrent workflows to complete..."
    sleep 5
    
    # Check results
    local completed=0
    local failed=0
    
    for workflow_id in "${workflows[@]}"; do
        status_response=$(curl -s "$BASE_URL/workflows/$workflow_id")
        current_state=$(echo "$status_response" | jq -r '.current_state')
        
        if [ "$current_state" == "COMPLETED" ] || [ "$current_state" == "FAILED" ]; then
            ((completed++))
        else
            ((failed++))
            warning "Workflow $workflow_id still in state: $current_state"
        fi
    done
    
    log "Concurrent execution results: $completed completed/failed, $failed inconclusive"
    
    if [ $completed -ge 2 ]; then
        success "Concurrent module execution test passed"
    else
        error "Concurrent module execution test failed"
    fi
}

# Test 3: Large Payload Handling
test_large_payloads() {
    log "=== Test 3: Large Payload Handling ==="
    
    # Create a large message
    local large_message=$(printf 'A%.0s' {1..10000})  # 10KB message
    payload="{\"message\": \"$large_message\"}"
    
    log "Sending large payload (${#large_message} bytes)..."
    
    response=$(curl -s -X POST "$BASE_URL/agent/$TEST_AGENT_ID/echo_module" \
        -H "Content-Type: application/json" \
        -d "$payload" -w "%{http_code}" -o /dev/null)
    
    if [ "$response" == "200" ]; then
        success "Large payload test passed"
    else
        error "Large payload test failed with HTTP code: $response"
    fi
}

# Test 4: Malformed Request Handling
test_malformed_requests() {
    log "=== Test 4: Malformed Request Handling ==="
    
    local test_cases=(
        '{"invalid_field": "value"}'  # Missing required fields
        '{"message": }'               # Invalid JSON
        ''                            # Empty payload
        '{"message": "test", "extra": "'$(printf 'A%.0s' {1..1000})'"}'  # Very large field
    )
    
    local passed=0
    local total=${#test_cases[@]}
    
    for i in "${!test_cases[@]}"; do
        payload="${test_cases[$i]}"
        log "Testing malformed payload #$((i+1))..."
        
        response=$(curl -s -X POST "$BASE_URL/agent/$TEST_AGENT_ID/echo_module" \
            -H "Content-Type: application/json" \
            -d "$payload" -w "%{http_code}" -o /dev/null)
        
        # Should get 400 or 422 for bad requests, not 500
        if [ "$response" != "500" ]; then
            ((passed++))
            log "  Payload #$((i+1)) handled correctly (HTTP $response)"
        else
            warning "  Payload #$((i+1)) caused server error (HTTP 500)"
        fi
    done
    
    log "Malformed request results: $passed/$total handled gracefully"
    
    if [ $passed -eq $total ]; then
        success "Malformed request handling test passed"
    else
        error "Malformed request handling test failed: $((total-passed)) payloads caused issues"
    fi
}

# Test 5: Rapid State Transitions
test_rapid_state_transitions() {
    log "=== Test 5: Rapid State Transitions ==="
    
    local workflow_ids=()
    local num_workflows=20
    
    log "Creating $num_workflows rapid workflows..."
    
    # Create multiple workflows quickly
    for i in $(seq 1 $num_workflows); do
        payload="{\"message\": \"Rapid state test $i\"}"
        response=$(curl -s -X POST "$BASE_URL/agent/$TEST_AGENT_ID/echo_module" \
            -H "Content-Type: application/json" \
            -d "$payload")
        workflow_id=$(echo "$response" | jq -r '.workflow_id')
        workflow_ids+=("$workflow_id")
        
        # Very small delay to create rapid succession
        usleep 100000  # 100ms
    done
    
    log "Waiting for rapid workflows to complete..."
    sleep 3
    
    # Check all workflows
    local completed=0
    local failed=0
    local pending=0
    
    for workflow_id in "${workflow_ids[@]}"; do
        status_response=$(curl -s "$BASE_URL/workflows/$workflow_id")
        current_state=$(echo "$status_response" | jq -r '.current_state')
        
        case "$current_state" in
            "COMPLETED")
                ((completed++))
                ;;
            "FAILED")
                ((failed++))
                ;;
            *)
                ((pending++))
                warning "Workflow $workflow_id in unexpected state: $current_state"
                ;;
        esac
    done
    
    log "Rapid state transition results: $completed completed, $failed failed, $pending pending"
    
    if [ $((completed+failed)) -eq $num_workflows ] && [ $pending -eq 0 ]; then
        success "Rapid state transitions test passed"
    else
        error "Rapid state transitions test failed"
    fi
}

# Test 6: Fault Injection
test_fault_injection() {
    log "=== Test 6: Fault Injection ==="
    
    # Test various fault scenarios
    local fault_scenarios=(
        '{"message": "Delay test", "delay": 5}'      # 5-second delay
        '{"message": "Crash test", "crash": true}'   # Intentional crash
        '{"message": "Normal test"}'                 # Normal execution
    )
    
    local scenario_names=("Delay" "Crash" "Normal")
    local results=()
    
    for i in "${!fault_scenarios[@]}"; do
        payload="${fault_scenarios[$i]}"
        scenario_name="${scenario_names[$i]}"
        
        log "Testing fault scenario: $scenario_name"
        
        response=$(curl -s -X POST "$BASE_URL/agent/$TEST_AGENT_ID/faulty_module" \
            -H "Content-Type: application/json" \
            -d "$payload")
        
        workflow_id=$(echo "$response" | jq -r '.workflow_id')
        
        if [ "$workflow_id" != "null" ] && [ -n "$workflow_id" ]; then
            # Wait for completion/failure
            sleep 7
            
            status_response=$(curl -s "$BASE_URL/workflows/$workflow_id")
            current_state=$(echo "$status_response" | jq -r '.current_state')
            results+=("$scenario_name:$current_state")
            
            log "  $scenario_name scenario resulted in state: $current_state"
        else
            error "  Failed to create workflow for $scenario_name scenario"
            results+=("$scenario_name:ERROR")
        fi
    done
    
    # Validate results
    local delay_result=$(echo "${results[0]}" | cut -d':' -f2)
    local crash_result=$(echo "${results[1]}" | cut -d':' -f2)
    local normal_result=$(echo "${results[2]}" | cut -d':' -f2)
    
    local passed=0
    
    # Delay scenario should complete
    if [ "$delay_result" == "COMPLETED" ] || [ "$delay_result" == "FAILED" ]; then
        ((passed++))
    fi
    
    # Crash scenario should fail
    if [ "$crash_result" == "FAILED" ]; then
        ((passed++))
    fi
    
    # Normal scenario should complete
    if [ "$normal_result" == "COMPLETED" ]; then
        ((passed++))
    fi
    
    log "Fault injection results: $passed/3 scenarios behaved as expected"
    
    if [ $passed -eq 3 ]; then
        success "Fault injection test passed"
    else
        error "Fault injection test failed: $((3-passed)) scenarios misbehaved"
    fi
}

# Test 7: Memory Pressure Simulation
test_memory_pressure() {
    log "=== Test 7: Memory Pressure Simulation ==="
    
    local workflow_ids=()
    local num_iterations=15
    
    log "Creating memory pressure with $num_iterations iterations..."
    
    # Create many small workflows rapidly to simulate memory pressure
    for i in $(seq 1 $num_iterations); do
        payload="{\"message\": \"Memory pressure test iteration $i\"}"
        response=$(curl -s -X POST "$BASE_URL/agent/$TEST_AGENT_ID/echo_module/async" \
            -H "Content-Type: application/json" \
            -d "$payload")
        
        workflow_id=$(echo "$response" | jq -r '.workflow_id')
        if [ "$workflow_id" != "null" ] && [ -n "$workflow_id" ]; then
            workflow_ids+=("$workflow_id")
        fi
        
        # Small delay to create sustained load
        usleep 50000  # 50ms
    done
    
    log "Created ${#workflow_ids[@]} async workflows, waiting for completion..."
    sleep 5
    
    # Check system health
    health_response=$(curl -s "$BASE_URL/")
    alive_agents=$(echo "$health_response" | jq '.alive_agents')
    total_agents=$(echo "$health_response" | jq '.total_agents')
    
    if [ "$alive_agents" -eq "$total_agents" ] && [ "$alive_agents" -gt 0 ]; then
        success "Memory pressure test passed - system remained healthy"
    else
        error "Memory pressure test failed - system health compromised"
        echo "$health_response" | jq '.'
    fi
}

# Test 8: Network Partition Simulation
test_network_partition() {
    log "=== Test 8: Network Partition Simulation ==="
    
    # This test simulates network issues by checking system resilience
    # when requests are made rapidly with varying delays
    
    log "Testing network resilience with varied timing..."
    
    local successful=0
    local total_tests=25
    
    for i in $(seq 1 $total_tests); do
        # Vary the request type
        case $((i % 3)) in
            0)
                payload='{"message": "Network test echo"}'
                endpoint="echo_module"
                ;;
            1)
                payload='{"host": "127.0.0.1", "count": 1}'
                endpoint="ping_module"
                ;;
            2)
                payload='{"message": "Network test fault", "delay": 0}'
                endpoint="faulty_module"
                ;;
        esac
        
        response=$(curl -s -X POST "$BASE_URL/agent/$TEST_AGENT_ID/$endpoint" \
            -H "Content-Type: application/json" \
            -d "$payload" -w "%{http_code}" -o /dev/null)
        
        if [ "$response" == "200" ]; then
            ((successful++))
        fi
        
        # Random delay to simulate network variability
        sleep $(echo "scale=3; $RANDOM/1000" | bc)
    done
    
    log "Network partition simulation results: $successful/$total_tests successful"
    
    # Allow some failures due to the aggressive testing
    if [ $successful -ge $((total_tests * 80 / 100)) ]; then
        success "Network partition simulation test passed"
    else
        error "Network partition simulation test failed: too many failures"
    fi
}

# Cleanup function
cleanup() {
    log "Cleaning up test resources..."
    # No specific cleanup needed for this test suite
    true
}

# Print summary
print_summary() {
    log "=== CHAOS TESTING SUMMARY ==="
    log "Passed tests: $PASSED_TESTS"
    log "Failed tests: $FAILED_TESTS"
    log "Total tests: $((PASSED_TESTS + FAILED_TESTS))"
    
    if [ $FAILED_TESTS -eq 0 ]; then
        success "All chaos tests passed! System is durable."
        exit 0
    else
        error "$FAILED_TESTS out of $((PASSED_TESTS + FAILED_TESTS)) tests failed."
        exit 1
    fi
}

# Main execution
main() {
    log "Starting chaos durability testing..."
    
    # Set up cleanup trap
    trap cleanup EXIT
    
    wait_for_server
    get_agent_id
    
    # Run all chaos tests
    test_request_flood
    test_concurrent_modules
    test_large_payloads
    test_malformed_requests
    test_rapid_state_transitions
    test_fault_injection
    test_memory_pressure
    test_network_partition
    
    print_summary
}

# Run main function
main "$@"