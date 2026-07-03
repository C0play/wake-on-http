"""Main entrypoint
"""

import os

from .api import Api
from .logger import logger


if __name__ == "__main__":
    api = Api()
    try:
        port = int(os.getenv("SERVER_PORT", "5000"))
        api.run(port)
    except Exception as e:
        logger.error(f"Failed to start Flask app: {e}")


