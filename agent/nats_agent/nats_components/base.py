import nats
from nats.errors import ConnectionClosedError
import json
import asyncio
import structlog

from typing import Callable

# Import metrics from the metrics module
from .. import metrics

class NATSComponent:
    """Base class for NATS interacting components."""
    
    def __init__(self, nc: nats.NATS, agent_id: str, agent_name: str):
        if nc is None:
            raise ValueError("NATS connection (nc) cannot be None")
        self.nc = nc
        self.agent_id = agent_id
        self.agent_name = agent_name
    
        # Get a logger specific to the component subclass name
        self.log = structlog.get_logger(component=self.__class__.__name__).bind(agent_id=agent_id)
    
        # Every NATSComonent will have some subject to subscribe/publish to
        self.subject = None 

        self.associated_subscriptions = []
        self.associated_publications = []

    def get_subject(self, ):
        if not self.subject:
            raise Exception("Component not created properly. No subject defined.")
        return self.subject.format(self=self, agent_id=self.agent_id, agent_name=self.agent_name)

class Publisher(NATSComponent):
    """Base class for components that publish messages."""
    
    def __init__(self, nc: nats.NATS, agent_id: str, agent_name: str, subject: str, error_handler: NATSComponent = None):
        super().__init__(nc, agent_id, agent_name)
        if not subject:
            raise ValueError("Publisher subject cannot be empty")
        self.subject = subject
        self.associated_publications.append(self.get_subject())

        self.error_handler = error_handler
        if error_handler:
            self.associated_publications.extend(error_handler.associated_publications)

        # Bind subject to logger context for this publisher instance
        self.log = self.log.bind(publish_subject=subject)

    async def publish(self, data: dict):
        """Publishes Python dict data as JSON to the defined NATS subject."""
        error_context = {"subject": self.get_subject(), "data_preview": str(data)[:100]}
        try:
            payload = json.dumps(data).encode('utf-8')
            await self.nc.publish(self.get_subject(), payload)
            metrics.MESSAGES_PUBLISHED.labels(subject=self.get_subject()).inc()
            # Limit logged data size for readability
            log_data_preview = str(data)[:200] + ('...' if len(str(data)) > 200 else '')
            self.log.debug("Published message", data_preview=log_data_preview, size_bytes=len(payload))
        except ConnectionClosedError as e:
            metrics.NATS_CONNECTION_STATUS.set(0)
            metrics.ERRORS_COUNTER.labels(type='nats_connection').inc()
            # Publish error traceback
            await self.error_handler.publish_error_traceback('publish_connection_closed', e, error_context)
        except TypeError as e:
            metrics.ERRORS_COUNTER.labels(type='serialization').inc()
            # Publish error traceback
            await self.error_handler.publish_error_traceback('publish_serialization', e, error_context)
        except Exception as e:
            metrics.ERRORS_COUNTER.labels(type='publish_error').inc()
            # Publish error traceback
            await self.error_handler.publish_error_traceback('publish_generic', e, error_context)

    async def start_publishing(self):
        """Subclasses can override this for continuous publishing loops."""
        self.log.warning("'start_publishing' called on generic Publisher, which does nothing by default.")
        # Placeholder to prevent accidental tight loops if called incorrectly
        await asyncio.sleep(1)

class Listener(NATSComponent):
    """Base class for components that listen for messages."""

    def __init__(self, nc: nats.NATS, agent_id: str, agent_name: str, subject: str, queue: str = "", error_handler: Callable = None):
        super().__init__(nc, agent_id, agent_name)
        if not subject:
            raise ValueError("Listener subject cannot be empty")
        self.subject = subject
        self.queue = queue # For queue subscribing
        self.associated_subscriptions.append(self.get_subject())
        
        self.error_handler = error_handler
        if error_handler:
            self.associated_publications.extend(error_handler.associated_publications)

        # Bind listen subject context
        self.log = self.log.bind(listen_subject=subject, queue_group=queue or 'default')

    async def message_handler(self, msg: nats.aio.msg.Msg):
        """Async callback to handle incoming NATS messages."""
        received_subject = msg.subject
        data_raw = msg.data
        data_str = None # Define here for use in context
        error_context = {"received_subject": received_subject, "raw_data_preview": str(data_raw[:100])}
        handler_log = self.log.bind(received_subject=received_subject)

        try:
            data_str = data_raw.decode('utf-8')
            error_context["decoded_data_preview"] = data_str[:100] # Update context
            data = json.loads(data_str)
            metrics.MESSAGES_RECEIVED.labels(subject=received_subject).inc()
            log_data_preview = data_str[:200] + ('...' if len(data_str) > 200 else '')
            handler_log.debug("Received message", data_preview=log_data_preview, size_bytes=len(data_raw))
            await self.process_message(received_subject, data) # process_message should handle its own errors
        except json.JSONDecodeError as e:
            metrics.ERRORS_COUNTER.labels(type='json_decode').inc()
            await self.error_handler.publish_error_traceback('message_json_decode', e, error_context)
        except UnicodeDecodeError as e:
             metrics.ERRORS_COUNTER.labels(type='unicode_decode').inc()
             await self.error_handler.publish_error_traceback('message_unicode_decode', e, error_context)
        except NotImplementedError as e:
            # Specifically catch if process_message is not implemented
            metrics.ERRORS_COUNTER.labels(type='message_handler_not_implemented').inc()
            await self.error_handler.publish_error_traceback('message_handler_not_implemented', e, error_context)
            # No need to re-raise usually, error is logged and published
        except Exception as e:
            # Catch errors within process_message if they weren't caught internally
            metrics.ERRORS_COUNTER.labels(type='message_handler_uncaught').inc()
            await self.error_handler.publish_error_traceback('message_handler_uncaught', e, error_context)

    async def process_message(self, subject: str, data: dict):
        """Subclasses MUST implement this method to define message processing logic."""
        self.log.warning("'process_message' not implemented by subclass", received_subject=subject)
        raise NotImplementedError(f"{self.__class__.__name__} must implement process_message")

    async def subscribe(self):
        """Subscribes to the defined NATS subject with the message handler."""
        subject = self.get_subject()
        error_context = {"subject": subject, "queue": self.queue}

        try:
            sub = await self.nc.subscribe(subject, queue=self.queue, cb=self.message_handler)
            self.log.info("Subscribed successfully")
            return sub
        except ConnectionClosedError as e:
            metrics.NATS_CONNECTION_STATUS.set(0)
            metrics.ERRORS_COUNTER.labels(type='nats_connection').inc()
            # Publish traceback BEFORE re-raising
            await self.error_handler.publish_error_traceback('subscribe_connection_closed', e, error_context)
            raise # Re-raise to indicate failure during startup
        except Exception as e:
            metrics.ERRORS_COUNTER.labels(type='subscribe_error').inc()
             # Publish traceback BEFORE re-raising
            await self.error_handler.publish_error_traceback('subscribe_generic', e, error_context)
            raise # Re-raise to indicate failure during startup
