import os

from abc import ABC, abstractmethod

from .logger import logger
from .config import NotificationServiceConfig, NtfyConfig


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NOTIFIERS_DIR = os.path.join(BASE_DIR, "notifiers")



class NotificationService(ABC):

    def __init__(self, config: NotificationServiceConfig) -> None:
        """Initialize the Service.

        Args:
            config: NotificationServiceConfig instance for this service.
        """
        filename = os.path.basename(config.file_metadata.path)
        self.name = os.path.splitext(filename)[0]
        self.cfg = config


    @abstractmethod
    def notify_event_wake(self, service: str, ip: str) -> None:
        ...

    
    @staticmethod
    @abstractmethod
    def string() -> str:
        ...



class NTFY(NotificationService):

    cfg: NtfyConfig

    def __init__(self, config: NtfyConfig) -> None:
        super().__init__(config)

    
    def notify_event_wake(self, service: str, ip: str) -> None:
        try:
            import requests

            data = f"Waking **{service}** for {ip}"
            headers = {
                "Title": "wake-on-http",
                "Markdown": "1",
                "Tags": "desktop_computer",
            }   
            requests.post(
                url=self.cfg.URL,
                data=data.encode(),
                headers=headers
            ).raise_for_status()

        except Exception as e:
            logger.error(f"Failed to send notification to {self.cfg.URL}: {e}")


    @staticmethod
    def string() -> str:
        return "ntfy"



class NotificationServiceRegistry:

    _notification_services: dict[str, NotificationService] = {}


    @classmethod
    def load_all(cls) -> None:
        for filename in os.listdir(NOTIFIERS_DIR):
            try:
                path = os.path.join(NOTIFIERS_DIR, filename)
                cfg = NtfyConfig.from_yaml(path)

                
                service = NTFY(cfg)
                cls._register(service)
            except ValueError as e:
                logger.warning(e)


    @classmethod
    def _register(cls, service: NotificationService):
        if service.name in cls._notification_services:
            raise ValueError(f"Tried to register {service.name} but it already exists")
            
        cls._notification_services[service.name] = service


    @classmethod
    def _unregister(cls, service: NotificationService):
        if service.name in cls._notification_services:
            del cls._notification_services[service.name]
        else:
            raise ValueError(f"Tried to unregister {service.name} but it doesn't exist")


    @classmethod
    def get(cls, names: str | list[str]) -> list[NotificationService]:
        if isinstance(names, str):
            names = [names]
        return [cls._notification_services[name] for name in names if name in cls._notification_services]
