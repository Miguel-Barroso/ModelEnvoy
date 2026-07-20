from __future__ import annotations

import argparse
import json
import sys

from .consult import consult


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="model-envoy",
        description="Consult an AI agent via OpenCode.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    consult_parser = sub.add_parser("consult", help="Send a prompt and print the response")
    consult_parser.add_argument("prompt", help="The prompt to send")
    consult_parser.add_argument(
        "--json", action="store_true", help="Output full result as JSON"
    )

    args = parser.parse_args()

    if args.command == "consult":
        result = consult(args.prompt)
        if args.json:
            output = json.dumps({
                "success": result.success,
                "response": result.response,
                "error": result.error,
                "metadata": result.metadata,
            }, indent=2)
            print(output)
        else:
            if result.success:
                print(result.response)
            else:
                print(f"Error: {result.error}", file=sys.stderr)
        sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()