import logging
import structlog
import sys

def setup_logging(log_level="INFO"):
    """Configures structlog based logging."""
    # Ensure standard logging is set up ONLY ONCE
    if not logging.root.handlers:
        logging.basicConfig(
            level=getattr(logging, log_level.upper(), logging.INFO),
            format="%(message)s", # structlog processors will handle the format
            stream=sys.stdout,    # Default to stdout
        )

    structlog.configure(
        processors=[
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter, # Required for standard logger
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure the formatter for the standard library handler
    formatter = structlog.stdlib.ProcessorFormatter(
        # These run ONCE per log event for the final output
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.TimeStamper(fmt="iso"),
            # Use ConsoleRenderer for dev, JSONRenderer for prod
            # structlog.processors.JSONRenderer()
            structlog.dev.ConsoleRenderer(colors=True), # Requires 'rich' library
        ],
        #foreign_pre_chain=shared_processors, # Optional: apply processors to non-structlog logs
    )

    # Apply the formatter to the root handler
    # (Assumes basicConfig created a StreamHandler)
    handler = logging.root.handlers[0]
    handler.setFormatter(formatter)

# Note: We don't instantiate the logger here.
# Other modules will import structlog and call structlog.get_logger()
# after setup_logging() has been called in main.py.