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
        
        options = {
            "bind": f"0.0.0.0:{port}",
            "workers": 1,
            "worker_class": "gevent",
        }
        
        Api(direct, port, options).run()
        
    except Exception as e:
        logger.error(f"Failed to start Flask app: {e}")
