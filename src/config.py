"""Configuration parsing and service config dataclasses.

This module provides a small dataclass-based representation of a service
configuration file and a helper to load that configuration from YAML.
"""

from dataclasses import dataclass, field
import yaml
import os


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
class ServiceConfig:
    """Representation of a service configuration loaded from YAML.

    Attributes:
        file_metadata: ``FileMetadata`` with path and mtime for the loaded config file.
        HOST_MAC, HOST_IP, APP_URL: Required values loaded directly from the YAML file.
        HOST_PORT: Port used for status checks (defaults to 22).
        IGNORED_PATHS: List of paths to ignore when handling requests.
        BROADCAST_IP: Broadcast address used for Wake-on-LAN packets.
    """

    file_metadata: FileMetadata

    # Required fields
    HOST_MAC : str
    HOST_IP : str
    APP_URL: str
    # Optional fields
    HOST_PORT: int = 22
    BROADCAST_IP: str = "255.255.255.255"
    IGNORED_PATHS: list[str] = field(default_factory=list)


    @classmethod
    def from_yaml(cls, path: str) -> "ServiceConfig":
        """Load and validate a YAML configuration file.

        Args:
            path: Path to the YAML file to load.

        Returns:
            ServiceConfig: A validated configuration instance.

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
        required_fields = ["HOST_MAC", "HOST_IP", "APP_URL"]
        for field in required_fields:
            if field not in data or data[field] is None:
                raise ValueError(f"Missing or empty required field '{field}' in {path}")

        # Ensure optional fields are not None
        if data.get("IGNORED_PATHS") is None:
            data["IGNORED_PATHS"] = []

        # Normalize ignored paths: strip leading slash to allow consistent comparisons
        data["IGNORED_PATHS"] = list(map(
            lambda p: p[1:] if isinstance(p, str) and p.startswith("/") else p,
            data["IGNORED_PATHS"]
        ))

        # File metadata
        mtime = os.path.getmtime(path)
        data["file_metadata"] = FileMetadata(path, mtime)

        return cls(**data)
