from unittest.mock import patch

import httpx
from pytest_httpx import HTTPXMock

from model_envoy import consult


BASE = "http://127.0.0.1:4096"


def test_consult_happy_path(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}/global/health", json={"healthy": True})
    httpx_mock.add_response(
        method="POST", url=f"{BASE}/session", json={"id": "s99", "title": ""}
    )
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE}/session/s99/message",
        json={
            "info": {"id": "m1", "role": "assistant"},
            "parts": [{"type": "text", "text": "Hello from OpenCode!"}],
        },
    )
    httpx_mock.add_response(
        method="DELETE", url=f"{BASE}/session/s99", status_code=200
    )

    result = consult("Hello")

    assert result.success is True
    assert result.response == "Hello from OpenCode!"
    assert result.error is None
    assert "latency_ms" in result.metadata


def test_consult_no_server(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}/global/health", status_code=503)

    with patch("model_envoy.transports.opencode._port_in_use") as port_check:
        port_check.return_value = True

        result = consult("Hello")
        assert result.success is False
        assert "in use" in result.error.lower()