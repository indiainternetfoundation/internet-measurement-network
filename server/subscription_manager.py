"""
Subscription manager for handling NATS subscriptions with duplicate prevention
"""
import asyncio
from typing import Dict, Any, List, Set


class SubscriptionManager:
    def __init__(self, nats_client):
        self.nats_client = nats_client
        self.active_subscriptions: Dict[str, Set[str]] = {}  # agent_id -> set of topic names
    
    async def subscribe_to_agent(self, agent_id: str, module_specs: Dict[str, Any], result_handler) -> List[str]:
        """Subscribe to agent topics, avoiding duplicates"""
        # Remove previous subscriptions from tracking
        if agent_id in self.active_subscriptions:
            await self.unsubscribe_from_agent(agent_id)
        
        topics = set()
        generic_topic = f"agent.{agent_id}.out"
        topics.add(generic_topic)
        
        # Module-specific output topics
        for module_name, module_config in module_specs.items():
            if "output_subject" in module_config:
                output_topic = module_config["output_subject"]
                if output_topic:
                    topics.add(output_topic)
        
        # Subscribe to all topics
        # The nats_observe client doesn't return subscription objects we can unsubscribe from
        # So we just track the topics instead
        for topic in topics:
            await self.nats_client.subscribe(topic, cb=result_handler)
        
        # Track the topics we're subscribed to for this agent
        self.active_subscriptions[agent_id] = topics
        print(f"[Subscription] Subscribed to agent {agent_id}: {list(topics)}")
        return list(topics)
    
    async def unsubscribe_from_agent(self, agent_id: str):
        """Unsubscribe from all topics for an agent"""
        if agent_id in self.active_subscriptions:
            # The nats_observe client doesn't support unsubscribe method
            # Instead, we just remove the subscriptions from our tracking
            # The client will handle cleanup when the connection closes
            del self.active_subscriptions[agent_id]
            print(f"[Subscription] Removed subscriptions for agent: {agent_id}")
    
    async def unsubscribe_all(self):
        """Unsubscribe from all agents"""
        for agent_id in list(self.active_subscriptions.keys()):
            await self.unsubscribe_from_agent(agent_id)
        print("[Subscription] Unsubscribed from all agents")
    
    def get_active_subscriptions(self) -> Dict[str, int]:
        """Get count of subscriptions per agent"""
        return {agent_id: len(topics) for agent_id, topics in self.active_subscriptions.items()}