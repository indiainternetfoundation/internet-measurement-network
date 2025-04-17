import typer
from pathlib import Path
import os
import asyncio
import structlog

# Import local modules
from .log_setup import setup_logging
from .config import load_or_create_config
from .core import run_agent # Import the core agent runner

# --- CLI Definition ---
app = typer.Typer(help="NATS Agent with Prometheus Metrics and Structlog Logging")

@app.command()
def main(
    # Config / Agent Identity
    config_dir: Path = typer.Option(
        Path("./__agent_data__"), # Default relative directory
        help="Directory to store the agent_config.ini file.",
        envvar="AGENT_CONFIG_DIR", # Allow setting via environment variable
        writable=True, # Ensure directory can be created if needed
        file_okay=False, # Must be a directory
        dir_okay=True,
        resolve_path=True, # Store absolute path
    ),
    agent_name: str = typer.Option(
        lambda: os.environ.get("AGENT_NAME", f"agent-{os.uname().nodename or 'unknown'}"), # Default using env var or hostname
        help="Logical name for this agent instance.",
        envvar="AGENT_NAME",
    ),

    # Nats Arguments
    nats_url: str = typer.Option(
        "nats://localhost:4222", # Default NATS URL
        help="NATS server URL(s), comma-separated if multiple.",
        envvar="NATS_URL",
    ),
    nats_account: str = typer.Option(
        None, # Default to no account specified
        help="NATS account (e.g., for JWT authentication - currently informational).",
        envvar="NATS_ACCOUNT",
    ),

    # Heartbeat Arguments
    heartbeat_subject: str = typer.Option(
        "agents.heartbeat",
        help="NATS subject for publishing heartbeat messages.",
        envvar="HEARTBEAT_SUBJECT",
    ),
    heartbeat_interval: int = typer.Option(
        5, # Default interval in seconds
        help="Interval (in seconds) between heartbeat messages.",
        envvar="HEARTBEAT_INTERVAL",
        min=1, # Ensure interval is positive
    ),

    # Prometheus Metrics Arguments
    metrics_port: int = typer.Option(
        9101, # Default Prometheus port
        help="Port for Prometheus metrics HTTP server (set to 0 to disable).",
        envvar="METRICS_PORT",
        min=0, # Allow 0 to disable
        max=65535,
    ),

    # Logging Level Argument
    log_level: str = typer.Option(
        "INFO",
        help="Set logging level (e.g., DEBUG, INFO, WARNING, ERROR, CRITICAL).",
        envvar="LOG_LEVEL",
        case_sensitive=False,
    )
):
    """
    Runs the NATS Agent. Connects to NATS, starts components,
    publishes heartbeats, and exposes Prometheus metrics.
    """
    # --- Setup ---
    # 1. Configure Logging (do this first!)
    setup_logging(log_level=log_level)
    log = structlog.get_logger("agent.main") # Get logger after setup

    # 2. Load or Create Configuration (Agent ID)
    try:
        config, agent_id = load_or_create_config(config_dir)
        # You could potentially load more settings overrides from 'config' here
        # e.g., nats_url = config.get('NATS', 'url', fallback=nats_url)
    except Exception as e:
        log.critical("Failed to load or create configuration.", path=config_dir, error=str(e), exc_info=True)
        raise typer.Exit(code=1) # Exit if config fails

    log.info(f"Starting Agent: '{agent_name}'", agent_id=agent_id, log_level=log_level)
    log.debug("Resolved Configuration:", **{ # Log debug info about settings
        "config_dir": str(config_dir),
        "agent_name": agent_name,
        "nats_url": nats_url,
        "nats_account": nats_account or "Not Set",
        "heartbeat_subject": heartbeat_subject,
        "heartbeat_interval": heartbeat_interval,
        "metrics_port": metrics_port or "Disabled",
    })


    # --- Run the Agent Core Logic ---
    try:
        asyncio.run(
            run_agent(
                nats_url = nats_url,
                nats_account = nats_account,
                agent_id = agent_id,
                agent_name = agent_name,
                heartbeat_subject=heartbeat_subject,
                heartbeat_interval=heartbeat_interval,
                metrics_port=metrics_port,
                # Pass other subjects if they become configurable
            )
        )
        log.info("Agent finished running normally.") # Should ideally not happen unless stopped externally
        raise typer.Exit(code=0)
    except KeyboardInterrupt:
        log.info("Shutdown requested via KeyboardInterrupt.")
        # asyncio.run() should handle cleanup via finally block in run_agent
        raise typer.Exit(code=0)
    except Exception as e:
        # Catch errors during asyncio.run or critical failures from run_agent
        log.critical("Agent stopped due to a critical error.", error=str(e), exc_info=True)
        raise typer.Exit(code=1) # Exit with error code

# --- Entry Point Check ---
# This allows running the module directly using `python -m nats_agent.main`
# or via the run_agent.py script.
if __name__ == "__main__":
     app()