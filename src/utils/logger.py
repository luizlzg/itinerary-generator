import os
import logging
from datetime import datetime

# Setup logging
def setup_logging():
    """Setup logging to file with detailed formatting."""
    log_dir = "./.logs"
    os.makedirs(log_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"itinerary_agent_{timestamp}.log")

    # Create logger
    logger = logging.getLogger("itinerary_agent")
    logger.setLevel(logging.DEBUG)

    # Remove existing handlers
    logger.handlers = []

    # File handler with detailed format
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)

    # Detailed formatter
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    return logger, log_file


# Initialize logger
LOGGER, LOG_FILE = setup_logging()
