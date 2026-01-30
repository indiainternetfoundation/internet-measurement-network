"""
Agent service - manages agent lifecycle and metadata
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

from models import AgentInfo
from db.persistence import PersistenceManager


class AgentService:
    """Manages agent lifecycle and metadata"""
    
    def __init__(self):
        self.agents: Dict[str, AgentInfo] = {}
        self.persistence = PersistenceManager() if PersistenceManager else None
        self._load_persistent_agents()
    
    def _load_persistent_agents(self) -> None:
        """Load agents from persistent storage on startup"""
        if self.persistence:
            try:
                persistent_agents = self.persistence.load_agents()
                for agent_id, agent in persistent_agents.items():
                    self.agents[agent_id] = agent
                print(f"[AgentService] Loaded {len(persistent_agents)} agents from persistent storage")
            except Exception as e:
                print(f"[AgentService] Warning: Could not load persistent agents: {e}")
    
    def sync_with_database(self) -> None:
        """Sync in-memory cache with database"""
        if self.persistence:
            try:
                # Load fresh data from database
                fresh_agents = self.persistence.load_agents()
                
                # Update in-memory cache with any new/updated entries
                updated_count = 0
                for agent_id, agent in fresh_agents.items():
                    if agent_id not in self.agents:
                        self.agents[agent_id] = agent
                        updated_count += 1
                    elif self.agents[agent_id] != agent:
                        self.agents[agent_id] = agent
                        updated_count += 1
                
                if updated_count > 0:
                    print(f"[AgentService] Synced {updated_count} agent updates from database")
                    
            except Exception as e:
                print(f"[AgentService] Warning: Could not sync with database: {e}")
    
    def update_heartbeat(self, agent_id: str, hostname: str, config: Dict) -> AgentInfo:
        """Update or create agent from heartbeat"""
        now = datetime.now(timezone.utc)
        
        if agent_id in self.agents:
            agent = self.agents[agent_id]
            agent.last_seen = now
            agent.alive = True
            agent.config = config
            agent.total_heartbeats += 1
            print(f"[AgentService] Updated: {agent_id}")
        else:
            agent = AgentInfo(
                agent_id=agent_id,
                alive=True,
                hostname=hostname,
                last_seen=now,
                config=config,
                first_seen=now,
                total_heartbeats=1
            )
            self.agents[agent_id] = agent
            print(f"[AgentService] Registered: {agent_id}")
        
        # Persist agent data
        if hasattr(self, 'persistence') and self.persistence:
            try:
                self.persistence.save_agent(agent)
            except Exception as e:
                print(f"[AgentService] Warning: Could not persist agent {agent_id}: {e}")
        
        return agent
    
    def mark_dead_agents(self, timeout_seconds: int) -> None:
        """Mark agents as dead if they haven't sent heartbeat"""
        now = datetime.now(timezone.utc)
        for agent_id, agent in self.agents.items():
            # Ensure last_seen is timezone-aware for comparison
            last_seen = agent.last_seen
            if last_seen.tzinfo is None:
                # If naive datetime, assume it's UTC
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            
            if agent.alive and (now - last_seen) > timedelta(seconds=timeout_seconds):
                agent.alive = False
                print(f"[AgentService] Marked dead: {agent_id}")
    
    def get(self, agent_id: str) -> Optional[AgentInfo]:
        """Get agent by ID"""
        return self.agents.get(agent_id)
    
    def get_alive(self) -> Dict[str, AgentInfo]:
        """Get all alive agents"""
        return {aid: agent for aid, agent in self.agents.items() if agent.alive}
    
    def get_dead(self) -> Dict[str, AgentInfo]:
        """Get all dead agents"""
        return {aid: agent for aid, agent in self.agents.items() if not agent.alive}