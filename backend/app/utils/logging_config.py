import logging
import os

DEFAULT_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

def configure_logging(level: str = DEFAULT_LEVEL):
    # Configure basic logging once. If already configured, this is a no-op for handlers.
    numeric_level = getattr(logging, level, logging.INFO)
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=numeric_level,
            format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        )

def get_logger(name: str):
    configure_logging()
    return logging.getLogger(name)
