#!/usr/bin/env python3
"""All entry effects are explicit input actions, never automatic enrichment."""
import argparse
import json
import os

from main import process_input


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="")
    args = parser.parse_args()
    payload = json.loads(args.data or os.environ.get("OPENLIA_MINION_INPUT_JSON", "{}"))
    result = process_input(payload)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
