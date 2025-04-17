import asyncio
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
from aiohttp import web
import structlog

log = structlog.get_logger("agent.metrics")

# --- Prometheus Metrics Definitions ---
MESSAGES_PUBLISHED = Counter(
    'agent_messages_published_total',
    'Total number of messages published',
    ['subject']
)
MESSAGES_RECEIVED = Counter(
    'agent_messages_received_total',
    'Total number of messages received',
    ['subject']
)
NATS_CONNECTION_STATUS = Gauge(
    'agent_nats_connection_status',
    'NATS connection status (1=connected, 0=disconnected)'
)
HEARTBEATS_SENT = Counter(
    'agent_heartbeats_sent_total',
    'Total number of heartbeats sent'
)
ERRORS_COUNTER = Counter(
    'agent_errors_total',
    'Total number of errors encountered',
    ['type'] # e.g., 'nats_connection', 'publish', 'subscribe', 'message_handler'
)

# --- Prometheus Server ---
async def metrics_handler(request):
    """aiohttp handler for Prometheus metrics."""
    try:
        resp = web.Response(body=generate_latest())
        resp.content_type = CONTENT_TYPE_LATEST
        return resp
    except Exception as e:
        log.error("Failed to generate metrics", error=str(e), exc_info=True)
        ERRORS_COUNTER.labels(type='metrics_generation').inc()
        # Return an error response
        return web.Response(status=500, text=f"Error generating metrics: {e}")


async def start_metrics_server(port: int):
    """Starts the Prometheus metrics server using aiohttp."""
    if port <= 0:
        log.info("Prometheus metrics server is disabled (port <= 0).")
        return

    app = web.Application()
    app.router.add_get('/metrics', metrics_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    try:
        await site.start()
        log.info("Prometheus metrics server started", port=port, url=f"http://0.0.0.0:{port}/metrics")
        # Keep it running until cancelled
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        log.info("Metrics server task cancelled.")
    except OSError as e:
        # Common error: Port already in use
        log.critical("Metrics server failed to start (OS Error)", port=port, error=str(e), exc_info=True)
        ERRORS_COUNTER.labels(type='metrics_server_start').inc()
        # Re-raise to potentially stop the agent if metrics are critical
        raise
    except Exception as e:
        log.error("Metrics server failed unexpectedly", error=str(e), exc_info=True)
        ERRORS_COUNTER.labels(type='metrics_server_runtime').inc()
    finally:
        log.info("Shutting down Prometheus metrics server")
        await runner.cleanup()
        log.info("Prometheus metrics server shut down complete.")