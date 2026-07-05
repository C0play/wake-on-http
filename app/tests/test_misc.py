import logging


from ..src.logger import _resolve_level


class TestMisc:

    def test_logger_no_env(self):

        assert _resolve_level("") == logging.DEBUG
