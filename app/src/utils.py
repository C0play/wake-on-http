"""Utility helpers used by the autostart plugin.

This module provides small helpers for checking host TCP reachability,
sending Wake-on-LAN packets and logging wake requests. Functions are
designed to be called from Flask request handlers and rely on
configuration provided by :class:`config.ServiceConfig`.
"""

import socket
import time
from urllib.parse import urlparse

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

    ip = cfg.HOST_IP
    port = cfg.HOST_PORT

    try:
        with socket.create_connection((ip, port), timeout=0.5):
            logger.debug(f"Checking {ip}:{port} status: host online")
            return True
    except OSError as e:
        logger.debug(f"Checking {ip}:{port} status: {e}")
        return False
    


def wake(cfg: ServiceConfig, identifier: str, ip: str):
    """Send a Wake-on-LAN packet for the configured host.

    This function enforces a short rate limit (40 seconds) per-MAC address
    to avoid repeated wake packets. It invokes the external ``wakeonlan``
    command with the configured broadcast IP and MAC address.

    Args:
        cfg: ServiceConfig with ``HOST_MAC`` and ``BROADCAST_IP``.
        identifier: Identifier of the service requesing the wake.
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

    __send_magic_packet(cfg.HOST_MAC)

    for notifier in NotificationServiceRegistry.get(cfg.NOTIFY):
            notifier.notify_event_wake(identifier, ip or "unknown")


def get_identifier(direct_service_netloc: str, url: str) -> str | None:

    parsed = urlparse(url)
    if not parsed.netloc:
        logger.warning(f"Could not determine network location from {url}")
        return None

    netloc = parsed.netloc
    netloc_path = parsed.netloc + parsed.path

    return (netloc_path if netloc == direct_service_netloc else netloc)


def __send_magic_packet(mac: str) -> None:
     
    spacers = [":", "-", "_", " "]
    try:
        if present := [x for x in spacers if x in mac]:
            for x in present:
                mac = mac.replace(x, "")

        if len(mac) > 12:
            logger.debug(f"Invalid mac: {mac}")
            return None
        
        mac = mac.lower()

        frame: bytes = bytes.fromhex("FF"*6 + mac*16)

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(frame, ("255.255.255.255", 7))
    except Exception as e:
         logger.exception(f"Failed to send magic packet for {mac}")
