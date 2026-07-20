from unittest.mock import MagicMock, patch

import httpx
import pytest
from pytest_httpx import HTTPXMock

from model_envoy import ConsultResult
from model_envoy.transports.opencode import OpenCodeTransport, _DEFAULT_PORT, _CleanFailure


BASE = f"http://127.0.0.1:{_DEFAULT_PORT}"


def _mock_healthy(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}/global/health", json={"healthy": True})


def _mock_session(httpx_mock: HTTPXMock, session_id: str = "s1") -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE}/session",
        json={"id": session_id, "title": ""},
    )


def _mock_message_response(httpx_mock: HTTPXMock, *texts: str) -> None:
    parts = [{"type": "text", "text": t} for t in texts]
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE}/session/s1/message",
        json={"info": {"id": "msg1", "role": "assistant"}, "parts": parts},
    )


_mock_text_response = _mock_message_response


def _mock_delete_session(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="DELETE", url=f"{BASE}/session/s1", status_code=200
    )


class TestSuccessfulConsult:
    def test_single_text_part(self, httpx_mock: HTTPXMock) -> None:
        _mock_healthy(httpx_mock)
        _mock_session(httpx_mock)
        _mock_text_response(httpx_mock, "reply from the model")
        _mock_delete_session(httpx_mock)

        result = OpenCodeTransport().consult("hello")

        assert result.success is True
        assert result.response == "reply from the model"
        assert result.error is None
        assert "latency_ms" in result.metadata

    def test_multiple_text_parts(self, httpx_mock: HTTPXMock) -> None:
        _mock_healthy(httpx_mock)
        _mock_session(httpx_mock)
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE}/session/s1/message",
            json={
                "parts": [
                    {"type": "text", "text": "line one"},
                    {"type": "text", "text": "line two"},
                ],
            },
        )
        _mock_delete_session(httpx_mock)

        result = OpenCodeTransport().consult("prompt")
        assert result.response == "line one\nline two"

    def test_non_text_parts_ignored(self, httpx_mock: HTTPXMock) -> None:
        _mock_healthy(httpx_mock)
        _mock_session(httpx_mock)
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE}/session/s1/message",
            json={
                "parts": [
                    {"type": "diagnostic", "data": "ignored"},
                    {"type": "text", "text": "the answer"},
                ],
            },
        )
        _mock_delete_session(httpx_mock)

        result = OpenCodeTransport().consult("prompt")
        assert result.response == "the answer"

    def test_empty_parts(self, httpx_mock: HTTPXMock) -> None:
        _mock_healthy(httpx_mock)
        _mock_session(httpx_mock)
        _mock_text_response(httpx_mock)
        _mock_delete_session(httpx_mock)

        result = OpenCodeTransport().consult("prompt")
        assert result.success is True
        assert result.response == ""


class TestTransportFailures:
    def test_http_timeout(self, httpx_mock: HTTPXMock) -> None:
        _mock_healthy(httpx_mock)
        _mock_session(httpx_mock)
        httpx_mock.add_exception(
            method="POST",
            url=f"{BASE}/session/s1/message",
            exception=httpx.TimeoutException("timed out"),
        )
        _mock_delete_session(httpx_mock)

        result = OpenCodeTransport().consult("prompt")
        assert not result.success
        assert "timed out" in result.error.lower()

    def test_http_500(self, httpx_mock: HTTPXMock) -> None:
        _mock_healthy(httpx_mock)
        _mock_session(httpx_mock)
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE}/session/s1/message",
            status_code=500,
        )
        _mock_delete_session(httpx_mock)

        result = OpenCodeTransport().consult("prompt")
        assert result.success is False
        assert "could not complete" in result.error.lower()

    def test_http_401(self, httpx_mock: HTTPXMock) -> None:
        _mock_healthy(httpx_mock)
        _mock_session(httpx_mock)
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE}/session/s1/message",
            status_code=401,
        )
        _mock_delete_session(httpx_mock)

        result = OpenCodeTransport().consult("prompt")
        assert result.success is False
        assert "could not complete" in result.error.lower()

    def test_provider_error_in_response(self, httpx_mock: HTTPXMock) -> None:
        _mock_healthy(httpx_mock)
        _mock_session(httpx_mock)
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE}/session/s1/message",
            json={
                "info": {"error": "DEGRADED function cannot be invoked"},
                "parts": [],
            },
        )
        _mock_delete_session(httpx_mock)

        result = OpenCodeTransport().consult("prompt")
        assert result.success is False
        assert "could not complete" in result.error.lower()

    def test_session_creation_failure(self, httpx_mock: HTTPXMock) -> None:
        _mock_healthy(httpx_mock)
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE}/session",
            status_code=503,
        )

        result = OpenCodeTransport().consult("prompt")
        assert result.success is False
        assert "session" in result.error.lower()

    def test_connection_lost_during_session_create(self, httpx_mock: HTTPXMock) -> None:
        _mock_healthy(httpx_mock)
        httpx_mock.add_exception(
            method="POST",
            url=f"{BASE}/session",
            exception=httpx.ConnectError("refused"),
        )

        result = OpenCodeTransport().consult("prompt")
        assert result.success is False
        assert "session" in result.error.lower()

    def test_connection_lost_during_message(self, httpx_mock: HTTPXMock) -> None:
        _mock_healthy(httpx_mock)
        _mock_session(httpx_mock)
        httpx_mock.add_exception(
            method="POST",
            url=f"{BASE}/session/s1/message",
            exception=httpx.ConnectError("lost"),
        )
        _mock_delete_session(httpx_mock)

        result = OpenCodeTransport().consult("prompt")
        assert result.success is False
        assert "connection" in result.error.lower()


class TestServerStartFailure:
    def test_port_in_use(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(url=f"{BASE}/global/health", status_code=503)

        with patch("model_envoy.transports.opencode._port_in_use") as port_check:
            port_check.return_value = True
            result = OpenCodeTransport().consult("prompt")
            assert result.success is False
            assert "in use" in result.error.lower()