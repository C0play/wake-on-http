"""Utility helpers used by the autostart plugin.

This module provides small helpers for checking host TCP reachability,
sending Wake-on-LAN packets and logging wake requests. Functions are
designed to be called from Flask request handlers and rely on
configuration provided by :class:`config.ServiceConfig`.
"""

import subprocess
import socket
import time

from .notify import NotificationServiceRegistry
from .config import ServiceConfig
from .logger import logger


# Store last wake timestamps to prevent multiple calls
_last_wakes: dict[str, float] = {}



def check_status(cfg: ServiceConfig) -> bool:
    """Check whether the configured host is reachable via TCP.

    Attempts a short-lived TCP connection to ``cfg.HOST_IP:cfg.HOST_PORT``.

    Args:
        cfg: ServiceConfig describing the target host and port.

    Returns:
        ``True`` if a TCP connection could be established, ``False`` otherwise.
    """

    hostname = cfg.HOST_IP
    port = cfg.HOST_PORT

    try:
        with socket.create_connection((hostname, port), timeout=0.5):
            logger.info(f"Checking {hostname}:{port} status: host online")
            return True
    except OSError as e:
        logger.info(f"Checking {hostname}:{port} status: {e}")
        return False
    


def wake(cfg: ServiceConfig, hostname: str, ip: str):
    """Send a Wake-on-LAN packet for the configured host.

    This function enforces a short rate limit (40 seconds) per-MAC address
    to avoid repeated wake packets. It invokes the external ``wakeonlan``
    command with the configured broadcast IP and MAC address.

    Args:
        cfg: ServiceConfig with ``HOST_MAC`` and ``BROADCAST_IP``.
        hostname: Hostname of the service requesing the wake.
        ip: IP address of the device requesting the wake.

    Raises:
        subprocess.CalledProcessError: if the ``wakeonlan`` command exits
            with a non-zero status.
        subprocess.TimeoutExpired: if the ``wakeonlan`` invocation times out.
    """
    current_time = time.time()
    last_wake = _last_wakes.get(cfg.HOST_MAC, 0)

    if current_time - last_wake < 50:
        logger.info(f"Wake for {cfg.HOST_IP} skipped (last wake {int(current_time - last_wake)}s ago)")
        return

    _last_wakes[cfg.HOST_MAC] = current_time

    logger.info(f"Waking {cfg.HOST_IP} via {cfg.BROADCAST_IP}")

    cmd = ["wakeonlan", "-i", cfg.BROADCAST_IP, cfg.HOST_MAC]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=0.1)

    for notifier in NotificationServiceRegistry.get(cfg.NOTIFY):
            notifier.send_wake(hostname, ip or "unknown")
