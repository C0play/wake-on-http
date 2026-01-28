"""Service registry and helper classes.

This module defines the :class:`Service` wrapper around a service
configuration and a :class:`ServiceFactory` that discovers, loads and
refreshes service configurations from the ``configs/`` directory.
"""

import os
import time
from urllib.parse import urlparse
from flask import (
    render_template, jsonify,
    make_response, request,
    Response, Request
)

from config import ServiceConfig
from logger import logger
import utils


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Service:
    """Represents a configured service and helper actions.
    """

    def __init__(self, config: ServiceConfig) -> None:
        """Initialize the Service.

        Args:
            config: ServiceConfig instance for this service.
        """
        filename = os.path.basename(config.file_metadata.path)
        self.name = os.path.splitext(filename)[0]
        self.cfg = config


    def check_status(self) -> bool:
        """Return True if the configured host is reachable.
        S
        Delegates to :func:`utils.check_status` which performs a TCP
        connection attempt to ``cfg.HOST_IP:cfg.HOST_PORT``.
        """
        return utils.check_status(self.cfg)


    def wake(self, request: Request) -> None:
        """Send a Wake-on-LAN packet for this service.

        Args:
            request: Flask request object that triggered the wake.
        """
        utils.wake(self.cfg, request)


    def should_ignore(self, path: str) -> bool:
        """Return True when the provided request path should be ignored.

        The incoming Flask ``path`` may start with ``/``; YAML-configured
        ignored paths are normalized without a leading slash, so this
        method strips a leading slash before comparing prefixes.

        Args:
            path: Request path (may start with '/').

        Returns:
            True if the path starts with any configured ignored prefix.
        """
        path = path[1:] if path.startswith('/') else path
        logger.debug(f"{path}, {self.cfg.IGNORED_PATHS}")

        return any(path.startswith(p) for p in self.cfg.IGNORED_PATHS)


    def respond(self, message: str, status: int = 200) -> tuple[Response, int]:
        """Return an appropriate Flask response for the service.

        If the client prefers HTML (``Accept`` contains ``text/html``), a
        service-specific template will be rendered if present, otherwise the
        ``default.html`` template is used. For non-HTML clients a JSON
        payload is returned.

        Args:
            message: Message to include in the JSON response.
            status: HTTP status code to return.

        Returns:
            A tuple of (response, status).
        """
        try:
            accept_header = request.headers.get("Accept", "")
            if "text/html" in accept_header:
                TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
                TEMPLATE_FILE = os.path.join(TEMPLATES_DIR, f"{self.name}.html")

                if os.path.exists(TEMPLATE_FILE):
                    template = render_template(f"{self.name}.html")
                else:
                    template = render_template(
                        f"default.html",
                        service_name=self.name
                    )

                response = make_response(template)
            else:
                response = jsonify({
                    "message": message,
                    "service_name": self.name,
                    "service_url": self.cfg.APP_URL
                })

            return response, status

        except Exception as e:
            logger.exception(e)
            return jsonify({"error": str(e)}), status



class ServiceRegistry:
    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._services: dict[str, Service] = {}
        self._hostname_map: dict[str, str] = {}


    def register(self, service: Service) -> None:
        """Register a service and update hostname mapping.

        If a service with the same name already exists it will be
        unregistered first.

        Args:
            service: Service instance to register.
        """
        if service.name in self._services:
            self.unregister(service.name)

        self._services[service.name] = service

        hostname = urlparse(service.cfg.APP_URL).hostname
        if hostname:
            self._hostname_map[hostname] = service.name


    def unregister(self, service_name: str) -> None:
        """Remove a registered service and its hostname mapping.

        Args:
            service_name: Name of the service to remove.

        Raises:
            KeyError: if the service is not present.
        """
        service = self._services.pop(service_name)

        hostname = urlparse(service.cfg.APP_URL).hostname
        if hostname and hostname in self._hostname_map:
            if self._hostname_map[hostname] == service_name:
                del self._hostname_map[hostname]


    def get_service_by_hostname(self, hostname: str) -> Service | None:
        """Return the :class:`Service` for the given hostname, or ``None``.

        Args:
            hostname: Request hostname (no port).

        Returns:
            The matching Service instance or ``None`` if not found.
        """
        service_name = self._hostname_map.get(hostname)
        if service_name:
            return self._services.get(service_name)
        return None


    def get_paths(self) -> list[str]:
        """Return list of config file paths for all registered services."""
        return [service.cfg.file_metadata.path for service in self._services.values()]


    def get_name(self, path: str) -> str:
        """Return the service name that references the given config path.

        Raises:
            ValueError: if multiple services reference the same path.
        """
        services = list(filter(lambda v: v.cfg.file_metadata.path == path, self._services.values()))
        if len(services) > 1:
            raise ValueError(f"Multiple services [{services}] reference the same config file: {path}")
        return services[0].name


    def get_mtimes(self) -> dict[str, float]:
        """Return a mapping of config path -> last_mtime for all services."""
        return {service.cfg.file_metadata.path: service.cfg.file_metadata.last_mtime 
                for service in self._services.values()}



class ServiceFactory:
    """Discover, load and manage configured services.

    The factory maintains a global :class:`ServiceRegistry` and provides
    convenience methods to load services from the ``configs/`` directory,
    refresh them when files change, and map request hostnames to services.
    """

    _service_registry: ServiceRegistry = ServiceRegistry()
    _last_refresh: float = 0

    # ==================== PUBLIC ====================

    @classmethod
    def load_all(cls):
        """Load all services from YAML files in the configs directory.

        This will reset any previously-registered services and create a new
        registry populated from files returned by :meth:`get_config_paths`.
        """
        
        # Reset all state
        cls._service_registry = ServiceRegistry()
        
        paths = ServiceFactory._get_config_paths()
        for path in paths:
            cls._add_service(path)


    @classmethod
    def get_service(cls, hostname: str) -> Service | None:
        """Return the service associated with the given hostname.

        Args:
            hostname: Request hostname (no port) to look up.

        Returns:
            The matching :class:`Service` instance or ``None`` if not found.
        """
        return cls._service_registry.get_service_by_hostname(hostname)


    @classmethod
    def refresh(cls) -> None:
        """Refresh registry: discover additions/removals and reload modified files.

        This method is rate-limited to avoid excessive filesystem checks; it
        returns quickly if invoked more frequently than once every 5 seconds.

        It performs three actions:
        - adds newly discovered config files,
        - removes services whose config files were deleted,
        - reloads services whose config file modification time changed.
        """
        if time.time() - cls._last_refresh < 5:
            return
        cls._last_refresh = time.time()
        

        #  Add new services
        if new_configs := cls._get_new_cfg_files():
            logger.info(f"Adding services with new config files:")
            for path in new_configs:
                logger.info(f"New config file: {path}")
                cls._add_service(path)


        # Remove services without config files
        if missing_configs:=  cls._get_missing_cfg_files():
            logger.info(f"Removing services with missing config files:")
            for service_name, path in missing_configs:
                logger.info(f"Config file removed: {path}")
                cls._remove_service(service_name)


        # Reload all services if necessary
        modified_configs = list(filter(
            lambda tp: tp[1] != ServiceFactory._get_curr_mtime(tp[0]),
            cls._service_registry.get_mtimes().items()
        ))
        logger.debug(f"modified_configs: {modified_configs}")
        if modified_configs:
            logger.info(f"Reloading services with modified config files:")
            
            for path, last_mtime in modified_configs:
                current_mtime = ServiceFactory._get_curr_mtime(path)
                service_name = cls._service_registry.get_name(path)
                logger.info(f"Config file changed: {path} (mtime {last_mtime} -> {current_mtime})")
                
                cls._remove_service(service_name)
                cls._add_service(path)



    # ==================== PRIVATE ====================

    @classmethod
    def _add_service(cls, config_path: str):
        """Load and register a service from a YAML config file.

        Args:
            config_path: Path to the service YAML file.

        Notes:
            Errors while parsing or registering the config are logged and
            do not raise; the service will be skipped on failure.
        """
        try:
            config = ServiceConfig.from_yaml(config_path)
            
            # Extract hostname from APP_URL
            hostname = urlparse(config.APP_URL).hostname
            
            if not hostname:
                logger.error(f"Could not determine hostname from APP_URL: \
                                   {config.APP_URL}")
                return

            new_service = Service(config)
            cls._service_registry.register(new_service)

            logger.info(f"Loaded service: {new_service.name} for host: {hostname}")
            
        except Exception as e:
            logger.error(f"Failed to load service from {config_path}: {e}")


    @classmethod
    def _remove_service(cls, service_name: str) -> None:
        """Unregister a service by name.

        Args:
            service_name: Name of the service to remove.
        """
        try:
            cls._service_registry.unregister(service_name)
        except KeyError:
            logger.warning(f"Tried to unregister {service_name} but it't not registered")


    # --- GETTERS ---

    @classmethod
    def _get_new_cfg_files(cls) -> list[str]:
        """Return list of config paths that are present on disk but not
        currently registered.
        """
        new_config_paths = ServiceFactory._get_config_paths()
        old_config_paths = cls._service_registry.get_paths()
        return list(set(new_config_paths) - set(old_config_paths))


    @classmethod
    def _get_missing_cfg_files(cls) -> list[tuple[str, str]]:
        """Return a list of (service_name, path) for services whose config
        files are no longer present on disk.
        """
        curr_config_paths = ServiceFactory._get_config_paths()
        registered_config_paths = cls._service_registry.get_paths()
        paths = list(set(registered_config_paths) - set(curr_config_paths))
        return [(cls._service_registry.get_name(path), path) for path in paths]


    @staticmethod
    def _get_config_paths() -> list[str]:
        """Return all YAML config file paths from the ``configs/`` directory.

        Returns:
            A list of absolute file paths ending with ``.yml``.
        """
        paths = [os.path.join(BASE_DIR, "configs", filename) for
             filename in os.listdir(os.path.join(BASE_DIR, "configs"))]
        return list(filter(lambda s: s.endswith(".yml"), paths))

    
    @staticmethod
    def _get_curr_mtime(path: str) -> float:
        """Return the modification time for *path* or ``0`` if inaccessible.

        Args:
            path: Filesystem path to stat.

        Returns:
            mtime as a float (seconds since epoch), or ``0`` if the file is
            missing or cannot be accessed.
        """
        try:
            new_mtime = os.path.getmtime(path)
            return new_mtime

        except OSError:  # File missing or inaccessible
            logger.warning(f"Failed to read {path}")
            return 0
