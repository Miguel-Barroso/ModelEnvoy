from unittest.mock import patch

import httpx
from pytest_httpx import HTTPXMock

from model_envoy import consult
from model_envoy.transports.opencode import _is_opencode_healthy, _port_in_use


BASE = "http://127.0.0.1:4096"


def test_opencode_already_running(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}/global/health", json={"healthy": True})
    assert _is_opencode_healthy(BASE) is True


def test_unrelated_app_on_port(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}/global/health", status_code=404)
    assert _is_opencode_healthy(BASE) is False


def test_nothing_on_port() -> None:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    assert _port_in_use(port) is False