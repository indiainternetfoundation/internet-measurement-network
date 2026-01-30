"""
Heartbeat sampler to reduce ClickHouse insertion frequency
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Any


class HeartbeatSampler:
    def __init__(self, sample_interval_seconds: int = 30):
        """
        Initialize heartbeat sampler
        
        Args:
            sample_interval_seconds: Minimum time between heartbeats to insert
        """
        self.sample_interval = timedelta(seconds=sample_interval_seconds)
        self.last_insertion: Dict[str, datetime] = {}  # agent_id -> last insertion time
    
    def should_insert_heartbeat(self, agent_id: str) -> bool:
        """
        Determine if a heartbeat should be inserted into ClickHouse
        
        Args:
            agent_id: The agent ID
            
        Returns:
            bool: True if heartbeat should be inserted, False to skip
        """
        now = datetime.now(timezone.utc)
        
        # First heartbeat for this agent
        if agent_id not in self.last_insertion:
            self.last_insertion[agent_id] = now
            return True
        
        # Check if enough time has passed since last insertion
        time_since_last = now - self.last_insertion[agent_id]
        
        if time_since_last >= self.sample_interval:
            self.last_insertion[agent_id] = now
            return True
        
        # Skip insertion - too soon
        return False
    
    def get_sampling_stats(self) -> Dict[str, Any]:
        """Get sampling statistics"""
        return {
            "sampling_interval_seconds": self.sample_interval.total_seconds(),
            "tracked_agents": len(self.last_insertion),
            "last_insertion_times": self.last_insertion
        }
    
    def cleanup_old_agents(self, max_age_minutes: int = 60):
        """
        Clean up agents that haven't sent heartbeats in a while
        
        Args:
            max_age_minutes: Maximum age in minutes before removing from tracking
        """
        now = datetime.now(timezone.utc)
        max_age = timedelta(minutes=max_age_minutes)
        
        agents_to_remove = []
        for agent_id, last_insertion in self.last_insertion.items():
            if now - last_insertion > max_age:
                agents_to_remove.append(agent_id)
        
        for agent_id in agents_to_remove:
            del self.last_insertion[agent_id]
        
        if agents_to_remove:
            print(f"[HeartbeatSampler] Cleaned up {len(agents_to_remove)} old agents")