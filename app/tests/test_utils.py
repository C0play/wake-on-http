import os
import time
import pytest
import unittest.mock

from flask import Request

from ..src.config import ServiceConfig, NtfyConfig
from ..src.notify import NTFY
from app.src.utils import check_status
from app.src import utils



class TestUtils:

    cwd = os.path.dirname(os.path.abspath(__file__))
    file = os.path.join(cwd, "mock_configs", "mock.yml")
    cfg = ServiceConfig.from_yaml(file)

    file = os.path.join(cwd, "mock_notifiers", "valid.yml")
    notifier = NTFY(NtfyConfig.from_yaml(file))

    # Fake flask.Request
    mock_request = unittest.mock.Mock(spec=Request)
    mock_request.url = "http://mock.local:8096"
    mock_request.headers = {"X-Forwarded-For": "1.1.1.1"}
    mock_request.remote_addr = "192.211.33.1"
    mock_request.host = "aaaa"


    @unittest.mock.patch("app.src.utils.socket.create_connection")
    def test_check_status_online(self, mock_create_conn):
        class DummyConn:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        mock_create_conn.return_value = DummyConn()

        assert check_status(self.cfg) is True


    @unittest.mock.patch("app.src.utils.socket.create_connection", side_effect=OSError("failed"))
    def test_check_status_offline(self, mock_create_conn):

        assert check_status(self.cfg) is False


    def test_spam_wake(self, caplog):

        now = time.time()
        with unittest.mock.patch("app.src.utils._last_wakes", {"00:00:00:00:00:00": now}):
            utils.wake(self.cfg, self.mock_request)

        assert "skipped" in caplog.text

    @unittest.mock.patch("app.src.utils._last_wakes", {})
    @unittest.mock.patch("app.src.utils.subprocess.run")
    @unittest.mock.patch("app.src.utils.NotificationServiceRegistry.get")
    def test_normal_wake(self, get, run, caplog):

        self.notifier.name = "test-wakes"
        get.return_value = [self.notifier]

        utils.wake(self.cfg, self.mock_request)

        assert "skipped" not in caplog.text
        assert "Failed to send notification" in caplog.text