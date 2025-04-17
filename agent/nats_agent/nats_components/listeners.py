import structlog

# Import base classes and metrics
from .base import Listener, Publisher
from .. import metrics

log = structlog.get_logger("agent.listeners")

class DataRequestListener(Listener):
    """Handles incoming requests on 'data.request'."""
    async def process_message(self, subject: str, data: dict):
        """Processes data requests and sends a response if 'reply_to' is present."""
        request_log = self.log.bind(received_subject=subject, request_id=data.get("request_id", "N/A"))
        request_log.info("Processing data request", request_data=data)

        # --- Example Logic: Process request ---
        # TODO: Replace with actual data processing logic
        processed_result = {"status": "processed", "received_data": data}
        # ------------------------------------

        # Send response if requested
        response_subject = data.get("reply_to")
        if response_subject:
             response_data = {
                 "status": "success",
                 "request_id": data.get("request_id"), # Echo back request ID
                 "result": processed_result
             }
             # Use a temporary Publisher instance for the response
             # Pass the NATS connection and agent_id from the listener
             response_publisher = Publisher(self.nc, self.agent_id, self.agent_name, response_subject)
             request_log.info("Sending response", reply_to=response_subject)
             await response_publisher.publish(response_data)
        else:
            request_log.info("No 'reply_to' field found, no response sent.")

class NotificationListener(Listener):
    """Handles incoming notifications on 'notifications.>'."""
    async def process_message(self, subject: str, data: dict):
        """Processes incoming notifications."""
        notification_log = self.log.bind(received_subject=subject)
        notification_log.info("Processing notification", notification_data=data)
        # TODO: Implement actual notification handling logic
        # e.g., update internal state, trigger other actions, etc.