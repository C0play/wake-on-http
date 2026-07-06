"""Main entrypoint
"""

import os

from .api import Api
from .logger import logger, _resolve_level


if __name__ == "__main__":
    try:
        direct = os.getenv("DIRECT", "")
        level = os.getenv("LOG_LEVEL", "DEBUG")
        port = int(os.getenv("SERVER_PORT", "5000"))
        
        logger.setLevel(_resolve_level(level))
        Api(direct).run(port)
        
    except Exception as e:
        logger.error(f"Failed to start Flask app: {e}")
