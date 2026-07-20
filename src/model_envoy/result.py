from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConsultResult:
    """The result of a `consult()` call.

    Attributes:
        success: Whether the server completed the request.
        response: The assistant's text reply, or `None` on failure.
        error: A human-readable error message, or `None` on success.
        metadata: Auxiliary diagnostics (e.g. latency_ms).
    """

    success: bool
    response: str | None
    error: str | None
    metadata: dict = field(default_factory=dict)