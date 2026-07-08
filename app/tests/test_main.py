import os
import pytest
import unittest.mock
import flask.testing 

from ..src.service import ServiceFactory, ServiceRegistry
from ..src.notify import NotificationServiceRegistry
from ..src.api import Api



@pytest.fixture
def client():
    app = Api("wake.com:5000").app
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

@pytest.fixture(scope="module", autouse=True)
def load_mock_services():
    cwd = os.path.dirname(os.path.abspath(__file__))
    service_configs_dir = os.path.join(cwd, "mock_configs")
    notifier_configs_dir = os.path.join(cwd, "mock_notifiers")

    with unittest.mock.patch("app.src.notify.NOTIFIERS_DIR", notifier_configs_dir), \
         unittest.mock.patch("app.src.notify.os.listdir", lambda _: ["test-wakes.yml"]), \
         unittest.mock.patch("app.src.service.ServiceFactory._get_config_paths") as get_config_paths:
        get_config_paths.return_value = [os.path.join(service_configs_dir, "mock.yml")]

        ServiceFactory.load_all()
        NotificationServiceRegistry.load_all()
        yield

    ServiceFactory._service_registry = ServiceRegistry()
    NotificationServiceRegistry._notification_services = {}


class TestValidRequest:

    def test_offline(self, client: flask.testing.FlaskClient, caplog):
        
        with unittest.mock.patch("app.src.service.check_status", return_value=False), \
             unittest.mock.patch("app.src.utils.__send_magic_packet"), \
             unittest.mock.patch("app.src.notify.NotificationServiceRegistry.get", return_value=[]):
            resp = client.get("/", base_url="http://mock.local:8096")

        assert resp.status_code == 202
        assert "Waking" in caplog.text
    
    
    def test_online(self, client: flask.testing.FlaskClient, caplog):
        
        with unittest.mock.patch("app.src.service.check_status", return_value=True):
            resp = client.get("/", base_url="http://mock.local:8096")

        assert resp.status_code == 302
        assert "Server online, redirecting to" in caplog.text


    def test_health(self, client: flask.testing.FlaskClient):

        with unittest.mock.patch("app.src.api.ServiceFactory.refresh") as refresh, \
             unittest.mock.patch("app.src.api.jsonify") as jsonify:

            resp = client.get("/health", base_url="http://wake.com:5000")
            
            refresh.assert_not_called()
            jsonify.assert_called_once()
            assert resp.status_code == 200


class TestInvalidRequest:

    def test_no_service(self, client: flask.testing.FlaskClient, caplog):

        resp = client.get("/", base_url="http://noservice.local:1234")

        assert resp.status_code == 404
        assert resp.json is not None
        assert "Service not found for" in resp.json["message"]
    
    
    def test_ignored(self, client: flask.testing.FlaskClient, caplog):

        resp = client.get("/ignore/me", base_url="http://mock.local:8096")

        assert resp.status_code == 503
        assert resp.json is not None
        assert "Server offline - background sync ignored" in resp.json["message"]

