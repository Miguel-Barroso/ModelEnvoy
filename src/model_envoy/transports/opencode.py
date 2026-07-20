from __future__ import annotations

import atexit
import logging
import os
import signal
import socket
import subprocess
import sys
import time
from typing import Any

import httpx

from .base import Transport
from ..result import ConsultResult

_logger = logging.getLogger(__name__)

_level = os.environ.get("MODEL_ENVOY_LOG")
if _level:
    logging.getLogger("model_envoy").setLevel(_level.upper())

_DEFAULT_PORT = 4096
_STARTUP_TIMEOUT = 20.0
_REQUEST_TIMEOUT = 120.0
_HEALTH_TIMEOUT = 5.0


def _port_in_use(port: int) -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except (ConnectionRefusedError, socket.timeout, OSError):
        return False


def _is_opencode_healthy(url: str, timeout: float = _HEALTH_TIMEOUT) -> bool:
    try:
        r = httpx.get(f"{url}/global/health", timeout=timeout)
        ok = r.status_code == 200
        if ok:
            _logger.debug("Health check passed for %s", url)
        else:
            _logger.debug("Health check returned %d for %s", r.status_code, url)
        return ok
    except Exception:
        _logger.debug("Health check failed (connection error) for %s", url)
        return False


class _ServerManager:
    """Manages the OpenCode server lifecycle for ModelEnvoy.

    Tries to connect to an existing server on port 4096.
    If none is found, launches one and tracks ownership for cleanup.
    """

    _instance: _ServerManager | None = None

    def __init__(self) -> None:
        self._started_by_us = False
        self._proc: subprocess.Popen[bytes] | None = None
        self._base_url = f"http://127.0.0.1:{_DEFAULT_PORT}"

    @classmethod
    def get(cls) -> _ServerManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def ensure_running(self) -> str:
        _logger.debug("Checking for OpenCode server at %s", self._base_url)
        if _is_opencode_healthy(self._base_url):
            _logger.info("Connected to existing OpenCode server at %s", self._base_url)
            return self._base_url
        _logger.info("No existing OpenCode server found. Launching one on port %d.",
                     _DEFAULT_PORT)
        return self._try_start()

    def _try_start(self) -> str:
        if _port_in_use(_DEFAULT_PORT):
            _logger.debug("Port %d is in use by something else.", _DEFAULT_PORT)
            raise _CleanFailure(
                f"Port {_DEFAULT_PORT} is in use by another application. "
                f"Stop the conflicting process to allow ModelEnvoy to start OpenCode."
            )

        env = os.environ.copy()
        env.setdefault("OPENCODE_SERVER_USERNAME", "opencode")

        preexec = os.setsid if sys.platform != "win32" else None
        self._proc = subprocess.Popen(
            ["opencode", "serve", "--port", str(_DEFAULT_PORT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            preexec_fn=preexec,
        )
        self._started_by_us = True
        _logger.info("Launched OpenCode server (pid %d) on port %d.",
                     self._proc.pid, _DEFAULT_PORT)

        deadline = time.monotonic() + _STARTUP_TIMEOUT
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                _logger.error("OpenCode server exited during startup (exit code %d).",
                              self._proc.returncode)
                raise _CleanFailure(
                    "OpenCode server exited during startup. "
                    "Check that OpenCode is installed and configured."
                )
            if _is_opencode_healthy(self._base_url):
                _logger.debug("OpenCode server healthy after %.1fs.",
                              _STARTUP_TIMEOUT - (deadline - time.monotonic()))
                return self._base_url
            time.sleep(0.15)

        self._kill_proc()
        self._started_by_us = False
        _logger.error("OpenCode server did not become healthy within %ds.",
                      _STARTUP_TIMEOUT)
        raise _CleanFailure(
            f"OpenCode server failed its health check "
            f"within {_STARTUP_TIMEOUT:.0f} seconds."
        )

    def _kill_proc(self) -> None:
        proc = self._proc
        if proc is None:
            return
        _logger.debug("Terminating OpenCode server (pid %d).", proc.pid)
        try:
            if sys.platform == "win32":
                proc.terminate()
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _logger.debug("Server did not terminate, sending SIGKILL.")
            try:
                proc.kill()
                proc.wait(timeout=3)
            except Exception:
                pass
        self._proc = None

    def shutdown(self) -> None:
        if not self._started_by_us:
            _logger.debug("Shutdown requested but server was not started by us.")
            return
        _logger.info("Shutting down OpenCode server started by ModelEnvoy.")
        self._kill_proc()
        self._started_by_us = False


_atexit_registered = False


def _register_atexit() -> None:
    global _atexit_registered
    if _atexit_registered:
        return
    _atexit_registered = True

    def _cleanup() -> None:
        mgr = _ServerManager._instance
        if mgr is not None:
            mgr.shutdown()

    atexit.register(_cleanup)
    _logger.debug("Registered atexit handler for server cleanup.")


class OpenCodeTransport(Transport):
    """Sends prompts via an auto-managed OpenCode server."""

    def consult(self, prompt: str) -> ConsultResult:
        start = time.monotonic()
        _logger.debug("Consult request received (%d chars).", len(prompt))

        _register_atexit()

        try:
            base_url = _ServerManager.get().ensure_running()
        except Exception as exc:
            _logger.error("Server start failed: %s", exc)
            return ConsultResult(
                success=False,
                response=None,
                error=str(exc),
            )

        client = httpx.Client(
            timeout=httpx.Timeout(10, read=_REQUEST_TIMEOUT),
        )

        session_id = self._ensure_session(client, base_url)
        if session_id is None:
            return ConsultResult(
                success=False,
                response=None,
                error="Unable to create a session with the OpenCode server.",
            )

        try:
            body: dict[str, Any] = {
                "parts": [{"type": "text", "text": prompt}],
            }
            _logger.debug("Sending message to session %s.", session_id)
            resp = client.post(
                f"{base_url}/session/{session_id}/message",
                json=body,
            )
        except httpx.TimeoutException:
            _logger.error("Request timed out for session %s.", session_id)
            self._delete_session(client, base_url, session_id)
            return self._failure("Request timed out.")
        except httpx.ConnectError:
            _logger.error("Connection lost while sending message.")
            self._delete_session(client, base_url, session_id)
            return self._failure("Lost connection to the OpenCode server.")
        except Exception as exc:
            _logger.error("Unexpected error sending message: %s", exc)
            self._delete_session(client, base_url, session_id)
            return self._failure(
                "Unable to send the request to the OpenCode server."
            )

        return self._process_response(client, base_url, session_id, resp, start)

    def _ensure_session(
        self, client: httpx.Client, base_url: str
    ) -> str | None:
        try:
            _logger.debug("Creating session.")
            response = client.post(f"{base_url}/session", json={})
            if not response.is_success:
                _logger.error("Session creation returned HTTP %d.", response.status_code)
                return None
            session_id = response.json()["id"]
            _logger.debug("Session %s created.", session_id)
            return session_id
        except httpx.ConnectError:
            _logger.error("Connection lost creating session.")
            return None
        except Exception as exc:
            _logger.error("Session creation failed: %s", exc)
            return None

    def _process_response(
        self,
        client: httpx.Client,
        base_url: str,
        session_id: str,
        response: httpx.Response,
        start: float,
    ) -> ConsultResult:
        if not response.is_success:
            _logger.error("Server returned HTTP %d.", response.status_code)
            self._delete_session(client, base_url, session_id)
            return self._failure(
                "The configured model could not complete the request."
            )

        data = response.json()

        error_info = (data.get("info") or {}).get("error")
        if error_info:
            _logger.error("Provider returned an error: %s", error_info)
            self._delete_session(client, base_url, session_id)
            return self._failure(
                "The configured model could not complete the request."
            )

        assistant_text = self._extract_text(data)
        self._delete_session(client, base_url, session_id)

        latency_ms = round((time.monotonic() - start) * 1000, 1)
        _logger.debug("Response received (%d chars, %d ms).",
                      len(assistant_text), latency_ms)
        return ConsultResult(
            success=True,
            response=assistant_text,
            error=None,
            metadata={"latency_ms": latency_ms},
        )

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        parts = data.get("parts", [])
        texts: list[str] = []
        for part in parts:
            if isinstance(part, dict) and part.get("type") == "text":
                texts.append(part.get("text", ""))
        return "\n".join(texts) if texts else ""

    @staticmethod
    def _delete_session(
        client: httpx.Client, base_url: str, session_id: str
    ) -> None:
        _logger.debug("Deleting session %s.", session_id)
        try:
            client.delete(
                f"{base_url}/session/{session_id}", timeout=10
            )
        except Exception:
            pass

    @staticmethod
    def _failure(message: str) -> ConsultResult:
        return ConsultResult(
            success=False,
            response=None,
            error=message,
        )


class _CleanFailure(Exception):
    """Internal exception for clean transport failures."""