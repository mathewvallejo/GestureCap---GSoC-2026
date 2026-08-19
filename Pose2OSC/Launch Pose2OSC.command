#!/bin/zsh
set -e

PROJECT_ROOT="${0:a:h}"
cd "$PROJECT_ROOT"

if [[ -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
else
  if [[ -z "$PYTHON" ]]; then
    if command -v python3.11 >/dev/null 2>&1; then
      PYTHON="python3.11"
    else
      PYTHON="python3"
    fi
  fi
  "$PYTHON" - <<'PY'
import sys

if sys.version_info < (3, 10):
    raise SystemExit("Pose2OSC requires Python 3.10 or newer.")
PY
  if [[ ! -d ".venv" ]]; then
    "$PYTHON" -m venv .venv
  fi
  PYTHON=".venv/bin/python"
fi

"$PYTHON" - <<'PY' || {
import importlib.util
import sys

missing = [
    module
    for module in ("cv2", "mediapipe", "pythonosc", "numpy")
    if importlib.util.find_spec(module) is None
]
sys.exit(1 if missing else 0)
PY
  "$PYTHON" -m pip install --upgrade pip
  "$PYTHON" -m pip install -e .
}

"$PYTHON" launch_pose2osc.py
