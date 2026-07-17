from .transports.opencode import invoke


def consult(prompt: str, mode: str | None = None) -> str:
    return invoke(prompt)