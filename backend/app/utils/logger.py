import logging
import sys

# Ensure UTF-8 output on Windows consoles to prevent UnicodeEncodeError with Persian characters
if hasattr(sys.stdout, "reconfigure"):
    try:
        stdout = sys.stdout
        getattr(stdout, "reconfigure")(encoding="utf-8", errors="replace")
    except Exception:
        pass


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
