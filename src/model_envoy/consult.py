from __future__ import annotations

from .result import ConsultResult
from .transports.opencode import OpenCodeTransport


def consult(prompt: str) -> ConsultResult:
    """Send a prompt to the configured model via OpenCode.

    ModelEnvoy automatically starts an OpenCode server if one is not
    already running on port 4096.  It reuses existing servers and only
    shuts down servers it started itself.

    Returns a `ConsultResult` — check `success` before consuming
    `response`.
    """
    transport = OpenCodeTransport()
    return transport.consult(prompt)