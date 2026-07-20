from .consult import consult
from .result import ConsultResult
from .transports.opencode import _ServerManager

__all__ = ["consult", "ConsultResult"]


def shutdown() -> None:
    """Gracefully stop the OpenCode server if ModelEnvoy started it.

    If ModelEnvoy connected to an already-running server, this is a no-op.
    """
    _ServerManager.get().shutdown()