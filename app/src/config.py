"""Configuration parsing and service config dataclasses.

This module provides a small dataclass-based representation of a service
configuration file and a helper to load that configuration from YAML.
"""

import yaml
import os

from typing import Any
from dataclasses import dataclass
from abc import ABC, abstractmethod

from .logger import logger



@dataclass
class FileMetadata:
    """Metadata about a configuration file on disk.

    Attributes:
        path: Filesystem path to the configuration file.
        last_mtime: Last modification time (as returned by :func:`os.path.getmtime`).
    """

    path: str
    last_mtime: float



@dataclass
class FileConfig(ABC):

    file_metadata: FileMetadata


    @classmethod
    @abstractmethod
    def from_yaml(cls, path: str) -> "FileConfig":
        ...


    @classmethod
    def _parse_yaml(cls,
            path: str,
            required_fields: list[str],
            optional_fields: dict[str, Any] = {}
        ) -> dict:
        
        """Load and validate a YAML configuration file.

        Args:
            path: Path to the YAML file to load.
            required_fields: Fields required to have a value set in the YAML file.
            optional_fields: Fields not required in the YAML file with their default values.

        Returns:
            data: A dictionary of fields and their (default) values.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file is empty, not a mapping, or missing required keys.
        """

        if not os.path.exists(path):
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, 'r') as f:
            data = yaml.safe_load(f)

        if data is None:
            raise ValueError(f"Config file {path} is empty")

        if not isinstance(data, dict):
            raise ValueError(f"Config file {path} must be a YAML dictionary")

        # Check for None values in required fields
        for field in required_fields:
            if field not in data or data[field] is None:
                raise ValueError(f"Missing or empty required field '{field}' in {path}")

        # Ensure optional fields are not None
        for field, default in optional_fields.items():
            data[field] = data.get(field) if data.get(field) else default

        # File metadata
        mtime = os.path.getmtime(path)
        data["file_metadata"] = FileMetadata(path, mtime)

        return data


    def has_changed(self) -> bool:
        return self.file_metadata.last_mtime != self._get_curr_mtime()


    def _get_curr_mtime(self) -> float:
        """Return the modification time for *path* or ``0`` if inaccessible.

        Args:
            path: Filesystem path to stat.

        Returns:
            mtime as a float (seconds since epoch), or ``0`` if the file is
            missing or cannot be accessed.
        """
        try:
            new_mtime = os.path.getmtime(self.file_metadata.path)
            return new_mtime

        except OSError:  # File missing or inaccessible
            logger.warning(f"Failed to read {self.file_metadata.path}")
            return 0



@dataclass
class ServiceConfig(FileConfig):
    """Representation of a service configuration loaded from YAML.

    Attributes:
        file_metadata: path and mtime for the loaded config file.
        HOST_MAC: MAC address of the service's host machine.
        HOST_IP: IP address of the service's host machine.
        APP_URL: Url of the service.
        HOST_PORT: Port used for status checks (defaults to 22).
        BROADCAST_IP: Broadcast address used for Wake-on-LAN packets.
        NOTIFY: List of notification services to use for notifications.
        IGNORED_PATHS: List of paths to ignore when handling requests.
    """

    # Required fields
    HOST_MAC : str
    HOST_IP : str
    APP_URL: str

    # Optional fields
    HOST_PORT: int
    BROADCAST_IP: str
    NOTIFY: list[str]
    IGNORED_PATHS: list[str]
    TIMEOUT: int


    @classmethod
    def from_yaml(cls, path: str, ) -> "ServiceConfig":
        """Load and validate a YAML configuration file.

        Args:
            path: Path to the YAML file to load.

        Returns:
            ServiceConfig: A validated configuration instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file is empty, not a mapping, or missing required keys.
        """

        data = super()._parse_yaml(
            path,
            ["HOST_MAC", "HOST_IP", "APP_URL"],
            {
                "TIMEOUT": 120,
                "HOST_PORT": 22,
                "BROADCAST_IP": "255.255.255.255",
                "IGNORED_PATHS": [],
                "NOTIFY": []
            }
        )

        # Normalize ignored paths: strip leading slash to allow consistent comparisons
        data["IGNORED_PATHS"] = list(map(
            lambda p: p[1:] if isinstance(p, str) and p.startswith("/") else p,
            data["IGNORED_PATHS"]
        ))

        return cls(**data)



@dataclass
class NotificationServiceConfig(FileConfig, ABC):
    """ Representation of a notification service configuration loaded from YAML.

    Attributes:
        file_metadata: ``FileMetadata`` with path and mtime for the loaded config file.
        type: Type of the notification service. Currently supported: ``[ntfy]``
    
    """

    # Required
    TYPE: str


    @classmethod
    def _parse_yaml(cls, path: str, required_fields: list[str], optional_fields: dict[str, Any] = {}) -> dict:
        required_fields.append("TYPE")
        return super()._parse_yaml(path, required_fields, optional_fields)



@dataclass
class NtfyConfig(NotificationServiceConfig):
    """Representation of an NTFY service configuration loaded from YAML.

    Attributes:
        file_metadata: ``FileMetadata`` with path and mtime for the loaded config file.
        type: Type of the notification service.
        url: URL of the server to send POST requests to
    """

    # Required
    URL: str


    @classmethod
    def from_yaml(cls, path: str) -> "NtfyConfig":
        """Load and validate a YAML configuration file.

        Args:
            path: Path to the YAML file to load.

        Returns:
            NtfyConfig: A validated configuration instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file is empty, not a mapping, or missing required keys.
        """

        data = super()._parse_yaml(path, ["URL"])

        return cls(**data)