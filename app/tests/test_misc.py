import unittest.mock
import unittest
import logging
import pytest
import time
import os


from ..src.logger import _resolve_level


class TestMisc:

    def test_logger_no_env(self):

        assert _resolve_level("") == logging.DEBUG
