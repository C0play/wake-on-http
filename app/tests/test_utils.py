import os
import time
import unittest.mock


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
            utils.wake(self.cfg, "mock", "1.1.1.1")

        assert "skipped" in caplog.text

    @unittest.mock.patch("app.src.utils._last_wakes", {})
    @unittest.mock.patch("app.src.utils.__send_magic_packet")
    @unittest.mock.patch("app.src.utils.NotificationServiceRegistry.get")
    def test_normal_wake(self, get, run, caplog):

        self.notifier.name = "test-wakes"
        get.return_value = [self.notifier]

        utils.wake(self.cfg, "mock", "1.1.1.1")

        assert "skipped" not in caplog.text
        assert "Failed to send notification" in caplog.text