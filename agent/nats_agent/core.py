import asyncio
import nats
from nats.errors import ConnectionClosedError, NoServersError, TimeoutError
import structlog

# Import local modules/components
from . import metrics
from .nats_components import (
    HeartbeatPublisher,
    DataRequestListener,
    NotificationListener,
    Publisher, # For startup message
    Listener,  # For type checking
    ErrorPublisher,
)

log = structlog.get_logger("agent.core")

# --- NATS Connection Callbacks ---
# Define callbacks as top-level async functions
async def nats_error_cb(e):
    """Logs NATS errors."""
    # Check if it's a "Connection Refused" during initial connect, which is common
    is_conn_refused = isinstance(e, OSError) and e.errno == 111 # errno 111 is Connection refused
    log_func = log.critical if not is_conn_refused else log.error
    log_func("NATS client error", error=str(e), error_type=type(e).__name__, exc_info=not is_conn_refused)
    metrics.ERRORS_COUNTER.labels(type='nats_error').inc()

async def nats_disconnected_cb():
    """Logs disconnection and updates status."""
    log.warning("NATS client disconnected.")
    metrics.NATS_CONNECTION_STATUS.set(0)

async def nats_closed_cb():
    """Logs connection closed and updates status."""
    log.warning("NATS connection closed.")
    metrics.NATS_CONNECTION_STATUS.set(0)

async def nats_reconnected_cb():
    """Logs reconnection and updates status."""
    log.info("NATS client reconnected.", server=nats.nc.connected_url.netloc if nats.nc and nats.nc.connected_url else "N/A")
    metrics.NATS_CONNECTION_STATUS.set(1)
    # Optional: Resubscribe if subscriptions were lost (depends on NATS server/client config)
    # Be careful with this, as the client library often handles resubscription.
    # Add logic here only if necessary and tested thoroughly.
    # log.info("Re-subscribing components...")
    # await _resubscribe_components_if_needed(nats.nc) # Example placeholder


# --- Core Agent Logic ---
async def run_agent(
    nats_url: str,
    agent_id: str,
    agent_name: str,
    heartbeat_subject: str,
    heartbeat_interval: int,
    metrics_port: int,
    nats_account: str = None, # Optional NATS account
    error_subject: str = "agent.{agent_id}.error",
    startup_subject: str = "agent.startup",
    request_subject: str = "data.request",
    notification_subject: str = "notifications.>",
    ):
    """Connects to NATS, starts components, and runs the agent."""

    log.info("Agent core starting", agent_id=agent_id, name=agent_name, nats_url=nats_url)
    nc = None
    metrics_task = None
    agent_tasks = []
    active_components = [] # Keep track of components for potential cleanup/resubscribe

    try:
        # --- Start Prometheus Metrics Server ---
        if metrics_port > 0:
            log.info("Attempting to start metrics server", port=metrics_port)
            metrics_task = asyncio.create_task(
                metrics.start_metrics_server(metrics_port),
                name="MetricsServer"
            )
        else:
            log.info("Metrics server disabled (port=0)")

        # --- Connect to NATS ---
        connect_opts = {
            "servers": nats_url.split(','),
            "name": f"{agent_name}-{agent_id[:8]}", # Unique client name
            "connect_timeout": 10,
            "reconnect_time_wait": 5,
            "max_reconnect_attempts": -1, # Keep trying
            "error_cb": nats_error_cb,
            "disconnected_cb": nats_disconnected_cb,
            "closed_cb": nats_closed_cb,
            "reconnected_cb": nats_reconnected_cb,
            "allow_reconnect": True,
            # Add credential/TLS options here if needed
        }
        if nats_account:
            # Verify correct NATS option for account/JWT etc.
            # connect_opts["user"] = nats_account # Example, check nats-py docs
            log.info("NATS account provided but currently not used in connect options.", account=nats_account)

        log.info("Connecting to NATS...", servers=connect_opts["servers"])
        nc = await nats.connect(**connect_opts)
        log.info("Connected to NATS", server=nc.connected_url.netloc if nc.connected_url else "N/A", client_id=nc.client_id)
        metrics.NATS_CONNECTION_STATUS.set(1)

        # --- Initialize Components ---
        log.info("Initializing NATS components...")
        error_publisher = ErrorPublisher(nc, agent_id, agent_name, error_subject,)
        heartbeat_publisher = HeartbeatPublisher(nc, agent_id, agent_name, heartbeat_subject, heartbeat_interval, error_handler=error_publisher)
        heartbeat_publisher.add_metadata(
            lambda : {
                "subscriptions": list(set([sub for x in active_components for sub in x.associated_subscriptions])) ,
                "publications":  list(set([sub for x in active_components for sub in x.associated_publications ])) ,
            }
        )

        request_listener = DataRequestListener(nc, agent_id, agent_name, request_subject, error_handler=error_publisher)
        notification_listener = NotificationListener(nc, agent_id, agent_name, notification_subject, error_handler=error_publisher)
        startup_publisher = Publisher(nc, agent_id, agent_name, startup_subject, error_handler=error_publisher)

        active_components.extend([
            heartbeat_publisher,
            request_listener,
            notification_listener,
            # Don't add startup_publisher if it only publishes once
        ])

        # --- Subscribe Listeners ---
        log.info("Subscribing listeners...")
        for component in active_components:
            if isinstance(component, Listener):
                await component.subscribe() # Handles its own logging/errors

        # --- Start Long-Running Publisher Tasks ---
        log.info("Starting background publisher tasks...")
        for component in active_components:
             # Check if it's a publisher with a non-default start_publishing method
             # (Specifically checking if it's the HeartbeatPublisher's implementation)
            if isinstance(component, HeartbeatPublisher):
                log.info(f"Creating task for {component.__class__.__name__}")
                task = asyncio.create_task(
                    component.start_publishing(),
                    name=f"{component.__class__.__name__}-{component.subject}" # Give task a name
                )
                agent_tasks.append(task)

        # --- Publish Startup Message ---
        await asyncio.sleep(1) # Brief pause to ensure subscriptions are active
        log.info("Publishing startup message", subject=startup_subject)
        await startup_publisher.publish({"message": f"Agent {agent_name} ({agent_id}) started successfully."})

        # --- Run Forever (or until a task fails) ---
        log.info("Agent core running. Monitoring tasks.")
        # Combine metrics task (if exists) with agent tasks for monitoring
        monitor_tasks = agent_tasks + ([metrics_task] if metrics_task else [])

        if not monitor_tasks:
             log.warning("No long-running tasks to monitor. Agent might exit prematurely.")
             # If there are no background tasks, wait indefinitely for NATS events
             await asyncio.Event().wait()
        else:
            done, pending = await asyncio.wait(
                monitor_tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Log results of completed tasks (usually indicates an error or unexpected exit)
            for task in done:
                try:
                    result = task.result() # Raise exception if task failed
                    log.warning("A monitored task completed unexpectedly.", task_name=task.get_name(), result=result)
                except asyncio.CancelledError:
                     log.info("A monitored task was cancelled.", task_name=task.get_name())
                except Exception as e:
                    log.error("A monitored task failed.", task_name=task.get_name(), error=str(e), exc_info=True)
                    metrics.ERRORS_COUNTER.labels(type='core_task_failure').inc()
                    # Optionally re-raise to stop the agent if a critical task fails
                    # raise


    # --- Handle Specific Connection Errors during Startup ---
    except NoServersError as e:
        log.critical("Could not connect to any NATS servers.", servers=nats_url, error=str(e))
        metrics.NATS_CONNECTION_STATUS.set(0)
        metrics.ERRORS_COUNTER.labels(type='nats_connect_failure').inc()
        # No point continuing if NATS connection failed initially
        raise # Re-raise to stop the application
    except TimeoutError as e:
        log.critical("Timeout occurred during initial NATS connection.", servers=nats_url, error=str(e))
        metrics.NATS_CONNECTION_STATUS.set(0)
        metrics.ERRORS_COUNTER.labels(type='nats_connect_timeout').inc()
        raise # Re-raise to stop the application
    except Exception as e:
        # Catch unexpected errors during setup/main loop
        log.critical("An unhandled error occurred in the agent core", error=str(e), exc_info=True)
        metrics.ERRORS_COUNTER.labels(type='unhandled_core_exception').inc()
        if metrics.NATS_CONNECTION_STATUS is not None: # Check if gauge exists
            metrics.NATS_CONNECTION_STATUS.set(0)
        raise # Re-raise to ensure the application exits on critical failure

    # --- Cleanup ---
    finally:
        log.info("Agent core shutting down...")
        if metrics.NATS_CONNECTION_STATUS is not None:
            metrics.NATS_CONNECTION_STATUS.set(0) # Mark as disconnected on shutdown

        # Combine metrics task (if exists) with agent tasks for cancellation
        all_tasks = agent_tasks + ([metrics_task] if metrics_task else [])

        # Cancel all running tasks gracefully
        for task in all_tasks:
            if task and not task.done():
                task.cancel()
                log.debug(f"Cancelling task: {task.get_name()}")

        # Wait for tasks to finish cancelling
        if all_tasks:
             # Gather results, suppressing CancelledError
             results = await asyncio.gather(*all_tasks, return_exceptions=True)
             for i, result in enumerate(results):
                 task_name = all_tasks[i].get_name() if i < len(all_tasks) else "UnknownTask"
                 if isinstance(result, asyncio.CancelledError):
                     log.debug(f"Task cancellation confirmed: {task_name}")
                 elif isinstance(result, Exception):
                      log.warning(f"Error during task shutdown: {task_name}", error=str(result), exc_info=isinstance(result, Exception)) # Log exception info
                 # else: log success if needed


        # Close NATS connection
        if nc and nc.is_connected:
            try:
                log.info("Draining NATS connection...")
                await nc.drain() # Publish pending messages, close subs gracefully
                log.info("NATS connection drained and closed.")
            except Exception as e:
                log.error("Error during NATS drain/close", error=str(e), exc_info=True)
        elif nc and not nc.is_closed:
             try:
                await nc.close()
                log.info("NATS connection closed (was not connected).")
             except Exception as e:
                 log.error("Error closing NATS connection", error=str(e))
        else:
            log.debug("NATS connection was not established or already closed.")

        log.info("Agent core shutdown complete.")