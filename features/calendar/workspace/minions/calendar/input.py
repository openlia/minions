#!/usr/bin/env python3
"""Parse one explicit Calendar Minion input action."""
import argparse
import json
import os

from main import process_input


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="")
    args = parser.parse_args()
    payload = json.loads(args.data or os.environ.get("OPENLIA_MINION_INPUT_JSON", "{}"))
    print(json.dumps(process_input(payload), ensure_ascii=False))


if __name__ == "__main__":
    main()
