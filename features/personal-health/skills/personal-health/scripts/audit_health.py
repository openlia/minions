#!/usr/bin/env python3
"""Run the canonical app's person-boundary audit without duplicating its logic."""
import os
from pathlib import Path
import runpy
import sys


if __name__ == "__main__":
    workspace = Path(os.environ.get("OPENLIA_WORKSPACE_ROOT", "/opt/data/workspace"))
    if "--workspace-root" in sys.argv:
        workspace = Path(sys.argv[sys.argv.index("--workspace-root") + 1])
    script = workspace / "minions/personal-health/audit_health.py"
    if "--self-test" in sys.argv and not script.is_file():
        script = Path(__file__).resolve().parents[3] / "workspace/minions/personal-health/audit_health.py"
    if not script.is_file():
        raise SystemExit("Install/update the Personal Health app before running its audit.")
    runpy.run_path(str(script), run_name="__main__")
