#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
INCLUDE_DEV="${INCLUDE_DEV:-1}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python interpreter not found: $PYTHON_BIN" >&2
  exit 1
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$ROOT_DIR/requirements.txt"

if [ "$INCLUDE_DEV" = "1" ]; then
  "$VENV_DIR/bin/python" -m pip install -r "$ROOT_DIR/requirements-dev.txt"
fi

if [ ! -f "$ROOT_DIR/.env" ]; then
  cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
fi

mkdir -p "$ROOT_DIR/data"

cat <<EOF
Installation complete.

Virtual environment: $VENV_DIR

Activate:
  source "$VENV_DIR/bin/activate"

Run the API:
  uvicorn src.main:app --reload

OpenClaw is optional and must be installed separately if you need browser-backed live scraping.
EOF
