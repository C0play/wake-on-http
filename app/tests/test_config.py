import unittest.mock
import unittest
import pytest
import time
import os

from ..src.config import ServiceConfig, NtfyConfig

        

class TestServiceCfg():

    cwd = os.path.dirname(os.path.abspath(__file__))
    configs_dir = os.path.join(cwd, "mock_configs")


    @pytest.mark.parametrize("exception, file", [
        (FileNotFoundError, "no_mock.yml"),
        (ValueError, "empty.yml"),
        (ValueError, "not_dict.yml"),
        (ValueError, "missing.yml")
    ])
    def test_parse_yaml(self, exception: type[Exception], file: str):

        with pytest.raises(exception):
            path = os.path.join(self.configs_dir, file)
            ServiceConfig.from_yaml(path)


    def test_has_not_changed(self):
        path = os.path.join(self.configs_dir, "mock.yml")
        assert ServiceConfig.from_yaml(path).has_changed() == False
    
    
    @unittest.mock.patch("app.src.config.ServiceConfig._get_curr_mtime")
    def test_has_changed(self, _get_curr_mtime):
        _get_curr_mtime.return_value = time.time()
        path = os.path.join(self.configs_dir, "mock.yml")
        assert ServiceConfig.from_yaml(path).has_changed() == True


    @pytest.mark.parametrize("file, not_zero", [
        ("mock.yml", True),
        ("no_mock.yml", False)
    ])
    def test_mtime(self, file: str, not_zero: bool):

        path = os.path.join(self.configs_dir, file)
        cfg = ServiceConfig.from_yaml(os.path.join(self.configs_dir, "mock.yml"))
        cfg.file_metadata.path = path

        assert not_zero | (cfg._get_curr_mtime() == 0)



class TestNotificationServiceCfg():

    cwd = os.path.dirname(os.path.abspath(__file__))
    configs_dir = os.path.join(cwd, "mock_notifiers")


    @pytest.mark.parametrize("exception, file", [
        (FileNotFoundError, "no_mock.yml"),
        (ValueError, "empty.yml"),
        (ValueError, "not_dict.yml"),
        (ValueError, "missing.yml"),
        (ValueError, "no_required.yml"),
    ])
    def test_parse_yaml(self, exception: type[Exception], file: str):

        with pytest.raises(exception):
            path = os.path.join(self.configs_dir, file)
            NtfyConfig.from_yaml(path)


    def test_parse_ok(self):
        path = os.path.join(self.configs_dir, "valid.yml")
        NtfyConfig.from_yaml(path)