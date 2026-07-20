# ModelEnvoy

Consult AI agents from AI agents.

```bash
model-envoy consult "Review this code for race conditions."
```

## CLI

```bash
model-envoy consult "Summarize this file in one paragraph."
```

Prints the response to stdout. Exit code 0 on success, 1 on failure.

```bash
model-envoy consult --json "Review this diff."   # structured output
```

## Python API

```python
from model_envoy import consult

result = consult("Review this code for race conditions.")

if result.success:
    print(result.response)
else:
    print(result.error)
```

## How it works

ModelEnvoy sends prompts to an OpenCode server. OpenCode forwards them to its configured model. ModelEnvoy never knows which model is being used — that is OpenCode's responsibility.

## Zero configuration

The only requirement is that OpenCode is installed and configured on your machine.

ModelEnvoy automatically starts an OpenCode server if one is not already running on port 4096. It reuses an existing server if one is found. It only shuts down servers that it started itself.

## Installation

From source:

```bash
pip install -e .
```

Or with pipx:

```bash
pipx install -e .
```

## Result object

```python
@dataclass
class ConsultResult:
    success: bool               # whether the request completed
    response: str | None        # the assistant's reply (when success is True)
    error: str | None           # human-readable error (when success is False)
    metadata: dict              # diagnostics (e.g. latency_ms)
```

## Error handling

All failures return a `ConsultResult(success=False, error="...")`. Raw exceptions are never exposed.

## Cleanup

```python
from model_envoy import shutdown

shutdown()
```

Only terminates servers that ModelEnvoy started itself.

## License

MIT