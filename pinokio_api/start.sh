#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${PINOKIO_VENV_DIR:-.venv}"

if [ -x "$VENV_DIR/bin/python" ]; then
  PYTHON="$VENV_DIR/bin/python"
elif [ -x "$VENV_DIR/Scripts/python.exe" ]; then
  PYTHON="$VENV_DIR/Scripts/python.exe"
else
  echo "Virtual environment not found. Run pinokio_api/install.sh first." >&2
  exit 1
fi

export PYTHONUNBUFFERED=1
export PYTHONPATH="$ROOT_DIR:${PYTHONPATH:-}"

exec "$PYTHON" -m src.main "$@"
