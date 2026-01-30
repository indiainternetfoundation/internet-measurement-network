"""
Workflow service - manages workflow state tracking
"""
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from db.persistence import PersistenceManager


class WorkflowService:
    """Manages workflow state tracking with only 3 states: RUNNING, COMPLETED, FAILED"""
    
    def __init__(self):
        # workflow_id -> workflow metadata
        self.workflows: Dict[str, Dict[str, Any]] = {}
        # workflow_id -> list of state transitions
        self.state_history: Dict[str, List[Dict[str, Any]]] = {}
        # workflow_id -> agent_id mapping for health checking
        self.workflow_agents: Dict[str, str] = {}
        # Add persistence
        self.persistence = PersistenceManager() if PersistenceManager else None
        self._load_persistent_workflows()
    
    def _load_persistent_workflows(self) -> None:
        """Load workflows from persistent storage on startup"""
        if self.persistence:
            try:
                persistent_workflows = self.persistence.load_workflows()
                self.workflows.update(persistent_workflows)
                
                persistent_states = self.persistence.load_workflow_states()
                self.state_history.update(persistent_states)
                
                print(f"[WorkflowService] Loaded {len(persistent_workflows)} workflows from persistent storage")
            except Exception as e:
                print(f"[WorkflowService] Warning: Could not load persistent workflows: {e}")
    
    def sync_with_database(self) -> None:
        """Sync in-memory cache with database"""
        if self.persistence:
            try:
                # Load fresh data from database
                fresh_workflows = self.persistence.load_workflows()
                fresh_states = self.persistence.load_workflow_states()
                
                # Update in-memory cache with any new/updated entries
                updated_count = 0
                for wf_id, wf_data in fresh_workflows.items():
                    if wf_id not in self.workflows:
                        self.workflows[wf_id] = wf_data
                        updated_count += 1
                    elif self.workflows[wf_id] != wf_data:
                        self.workflows[wf_id] = wf_data
                        updated_count += 1
                
                # Update state history
                for wf_id, states in fresh_states.items():
                    if wf_id not in self.state_history:
                        self.state_history[wf_id] = states
                        updated_count += 1
                    elif self.state_history[wf_id] != states:
                        self.state_history[wf_id] = states
                        updated_count += 1
                
                if updated_count > 0:
                    print(f"[WorkflowService] Synced {updated_count} updates from database")
                    
            except Exception as e:
                print(f"[WorkflowService] Warning: Could not sync with database: {e}")
    
    def create_workflow(self, workflow_id: str, agent_id: str, module_name: str, 
                       request: Dict[str, Any]) -> None:
        """Initialize a new workflow with RUNNING state"""
        workflow_data = {
            "agent_id": agent_id,
            "module_name": module_name,
            "request": request,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        self.workflows[workflow_id] = workflow_data
        self.workflow_agents[workflow_id] = agent_id  # Track which agent handles this workflow
        
        self.state_history[workflow_id] = [{
            "state": "RUNNING",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }]
        
        print(f"[Workflow] Created {workflow_id}: RUNNING")
        
        # Persist workflow data
        if hasattr(self, 'persistence') and self.persistence:
            try:
                self.persistence.save_workflow(workflow_id, workflow_data)
                self.persistence.save_workflow_state(
                    workflow_id, 
                    "RUNNING", 
                    datetime.now(timezone.utc).isoformat()
                )
            except Exception as e:
                print(f"[WorkflowService] Warning: Could not persist workflow {workflow_id}: {e}")
    
    def set_state(self, workflow_id: str, state: str, **metadata) -> None:
        """Set workflow state - only RUNNING, COMPLETED, or FAILED allowed"""
        if state not in ["RUNNING", "COMPLETED", "FAILED"]:
            raise ValueError(f"Invalid state: {state}. Must be RUNNING, COMPLETED, or FAILED")
        
        if workflow_id not in self.state_history:
            self.state_history[workflow_id] = []
        
        timestamp = datetime.now(timezone.utc).isoformat()
        state_entry = {
            "state": state,
            "timestamp": timestamp,
            **metadata
        }
        self.state_history[workflow_id].append(state_entry)
        print(f"[Workflow] {workflow_id}: {state}")
        
        # If workflow is completing/failing, remove from agent tracking
        if state in ["COMPLETED", "FAILED"] and workflow_id in self.workflow_agents:
            del self.workflow_agents[workflow_id]
        
        # Persist state transition
        if hasattr(self, 'persistence') and self.persistence:
            try:
                self.persistence.save_workflow_state(workflow_id, state, timestamp, metadata)
            except Exception as e:
                print(f"[WorkflowService] Warning: Could not persist state for {workflow_id}: {e}")
    
    def check_stale_workflows(self, agent_service) -> None:
        """Check for workflows assigned to dead agents and mark them as failed"""
        try:
            # Get current running workflows
            running_workflows = []
            for workflow_id, states in self.state_history.items():
                if states and states[-1]["state"] == "RUNNING":
                    running_workflows.append(workflow_id)
            
            # Check if agents for these workflows are still alive
            for workflow_id in running_workflows:
                if workflow_id in self.workflow_agents:
                    agent_id = self.workflow_agents[workflow_id]
                    agent = agent_service.get(agent_id)
                    
                    # If agent doesn't exist or is dead, mark workflow as failed
                    if not agent or not agent.alive:
                        print(f"[Workflow] Marking {workflow_id} as FAILED due to dead agent {agent_id}")
                        self.set_state(
                            workflow_id, 
                            "FAILED", 
                            reason="Agent died or disconnected",
                            agent_id=agent_id
                        )
        except Exception as e:
            print(f"[WorkflowService] Error checking stale workflows: {e}")
    
    def get_current_state(self, workflow_id: str) -> Optional[str]:
        """Get current state of a workflow"""
        history = self.state_history.get(workflow_id, [])
        return history[-1]["state"] if history else None