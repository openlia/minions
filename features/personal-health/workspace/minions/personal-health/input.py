#!/usr/bin/env python3
import argparse
import json
import os

from main import record_entry


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate and save a person-scoped health record")
    parser.add_argument("--data", default="")
    args = parser.parse_args()
    print(json.dumps(record_entry(json.loads(args.data or os.environ.get("OPENLIA_MINION_INPUT_JSON", "{}")))))
