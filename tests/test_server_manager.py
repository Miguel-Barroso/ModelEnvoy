from unittest.mock import MagicMock, patch

import pytest

from model_envoy.transports.opencode import (
    _ServerManager,
    _CleanFailure,
    _DEFAULT_PORT,
)


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    _ServerManager._instance = None
    yield
    _ServerManager._instance = None


@pytest.fixture
def manager() -> _ServerManager:
    return _ServerManager.get()


class TestExistingServer:
    def test_reuse_existing_server(self, manager: _ServerManager) -> None:
        with patch("model_envoy.transports.opencode._is_opencode_healthy") as health:
            health.return_value = True
            url = manager.ensure_running()
            assert url == f"http://127.0.0.1:{_DEFAULT_PORT}"
            assert manager._started_by_us is False

    def test_shutdown_noop_on_existing(self, manager: _ServerManager) -> None:
        with patch("model_envoy.transports.opencode._is_opencode_healthy") as health:
            health.return_value = True
            manager.ensure_running()
            manager.shutdown()
            assert manager._started_by_us is False
            assert manager._proc is None


class TestAutoLaunch:
    def test_launch_when_no_server(self, manager: _ServerManager) -> None:
        with patch("model_envoy.transports.opencode._is_opencode_healthy") as health, \
             patch("model_envoy.transports.opencode._port_in_use") as port_check, \
             patch("model_envoy.transports.opencode.subprocess.Popen") as popen, \
             patch("model_envoy.transports.opencode.os.setsid", None, create=True):

            health.side_effect = [False, True]  # fail, then healthy
            port_check.return_value = False
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_proc.poll.return_value = None
            popen.return_value = mock_proc

            url = manager.ensure_running()

            assert url == f"http://127.0.0.1:{_DEFAULT_PORT}"
            assert manager._started_by_us is True
            assert manager._proc is mock_proc
            popen.assert_called_once()

    def test_shutdown_kills_owned_server(self, manager: _ServerManager) -> None:
        with patch("model_envoy.transports.opencode._is_opencode_healthy") as health, \
             patch("model_envoy.transports.opencode._port_in_use") as port_check, \
             patch("model_envoy.transports.opencode.subprocess.Popen") as popen, \
             patch("model_envoy.transports.opencode.os.setsid", None, create=True):

            health.side_effect = [False, True]
            port_check.return_value = False
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_proc.poll.return_value = None
            popen.return_value = mock_proc

            manager.ensure_running()
            manager.shutdown()

            assert manager._started_by_us is False

    def test_port_in_use_by_other_app(self, manager: _ServerManager) -> None:
        with patch("model_envoy.transports.opencode._is_opencode_healthy") as health, \
             patch("model_envoy.transports.opencode._port_in_use") as port_check:

            health.return_value = False
            port_check.return_value = True

            with pytest.raises(_CleanFailure, match="in use by another"):
                manager.ensure_running()

    def test_process_exits_during_startup(self, manager: _ServerManager) -> None:
        with patch("model_envoy.transports.opencode._is_opencode_healthy") as health, \
             patch("model_envoy.transports.opencode._port_in_use") as port_check, \
             patch("model_envoy.transports.opencode.subprocess.Popen") as popen, \
             patch("model_envoy.transports.opencode.os.setsid", None, create=True):

            health.return_value = False
            port_check.return_value = False
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_proc.poll.return_value = 1  # exited
            mock_proc.returncode = 1
            popen.return_value = mock_proc

            with pytest.raises(_CleanFailure, match="exited during startup"):
                manager.ensure_running()

    def test_health_timeout(self, manager: _ServerManager) -> None:
        with patch("model_envoy.transports.opencode._is_opencode_healthy") as health, \
             patch("model_envoy.transports.opencode._port_in_use") as port_check, \
             patch("model_envoy.transports.opencode.subprocess.Popen") as popen, \
             patch("model_envoy.transports.opencode.os.setsid", None, create=True), \
             patch("model_envoy.transports.opencode.time.sleep") as sleep, \
             patch("model_envoy.transports.opencode.time.monotonic") as mono:

            health.return_value = False
            port_check.return_value = False
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_proc.poll.return_value = None
            popen.return_value = mock_proc
            mono.side_effect = [0, 21]  # simulate 21 seconds elapsed

            with pytest.raises(_CleanFailure, match="failed its health check"):
                manager.ensure_running()

            assert manager._started_by_us is False