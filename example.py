#!/usr/bin/env -S python3 -X utf8
"""Run from the project root:

    .venv/bin/python example.py

ModelEnvoy starts OpenCode automatically. No manual setup needed.
"""

import json
import sys

sys.path.insert(0, "src")

from model_envoy import consult

prompt = "In 1-2 sentences, explain what a race condition is in concurrent programming."

result = consult(prompt)

print(json.dumps({
    "success": result.success,
    "response": result.response,
    "error": result.error,
    "metadata": result.metadata,
}, indent=2))

sys.exit(0 if result.success else 1)