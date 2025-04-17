import nats
import json
import structlog
import traceback
import datetime
from nats.errors import ConnectionClosedError, NoServersError, TimeoutError

# Import base class and metrics
from .base import Publisher
from .. import metrics

class ErrorPublisher(Publisher):
    """Publishes agent status periodically."""
    def __init__(self, nc: nats.NATS, agent_id: str, agent_name: str, subject: str, ):
        super().__init__(nc, agent_id, agent_name, subject)

        # Bind additional context to the logger for this specific component
        self.log = self.log.bind(agent_name=agent_name, )


    # --- Error Publishing Helper ---
    async def publish_error_traceback(
        self, # NATS connection can be None if error occurs before connect
        error_type: str,    # A category for the error (e.g., 'publish', 'subscribe')
        error: Exception,   # The exception object itself
        context: dict | None = None # Optional dictionary for extra context
        ):
        """Formats exception info and publishes it to a NATS subject."""
        # Always format traceback, even if publish fails (useful for local logs)
        try:
            tb_string = traceback.format_exc()
            error_message = str(error)
            error_class = type(error).__name__
        except Exception as format_err:
            # Fallback if formatting itself fails
            log.error("Critical: Failed even to format traceback!", internal_error=str(format_err))
            tb_string = f"Traceback formatting failed: {format_err}"
            error_message = str(error) # Use original error message if possible
            error_class = type(error).__name__

        # Log the error locally first using structlog (this happens regardless of NATS)
        # Pass exc_info=error to let structlog handle standard exception logging
        self.log.error(
            f"Error occurred [{error_type}] - attempting to publish traceback",
            error_type=error_type,
            error_class=error_class,
            error_message=error_message,
            publish_context=context or {},
            exc_info=error # Let structlog format the exception for console/file logs
        )

        # --- Attempt to publish to NATS ---
        if self.nc is None or not self.nc.is_connected:
            self.log.warning(
                "Cannot publish error traceback: NATS connection unavailable.",
                target_subject=subject.format(agent_id="<unknown_id>" if not self.agent_id else self.agent_id),
                original_error_type=error_type
            )
            return # Exit if no connection

        error_subject = self.get_subject().format(self=self, agent_id=self.agent_id, agent_name=self.agent_name)
        payload = {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "timestamp_utc": datetime.datetime.utcnow(),
            "error_type": error_type, # User-defined category
            "error_class": error_class,
            "error_message": error_message,
            "traceback": tb_string,
            "context": context or {},
        }

        try:
            # Use ensure_future for fire-and-forget, but handle potential errors during publish
            payload_bytes = json.dumps(payload, indent=2).encode('utf-8') # Indent for readability on receiver
            await self.nc.publish(error_subject, payload_bytes)
            self.log.info("Successfully published error traceback", nats_subject=error_subject, original_error_type=error_type)
        except Exception as pub_err:
            # CRITICAL: Avoid recursion if publishing the error itself fails!
            # Log a warning, do not attempt to publish *this* error.
            self.log.warning(
                "Failed to publish error traceback to NATS",
                nats_subject=error_subject,
                original_error_type=error_type,
                publish_error_class=type(pub_err).__name__,
                publish_error=str(pub_err),
                # Do NOT add exc_info=True here to prevent loops
            )
            # Optionally increment a specific metric for error reporting failures
            metrics.ERRORS_COUNTER.labels(type='error_publish_failure').inc()
