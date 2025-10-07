#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${PINOKIO_VENV_DIR:-.venv}"

if [ ! -d "$VENV_DIR" ]; then
  echo "[pinokio] creating virtual environment in $VENV_DIR"
  PYTHON_BOOTSTRAP="${PINOKIO_PYTHON_BIN:-python3}"
  if ! command -v "$PYTHON_BOOTSTRAP" >/dev/null 2>&1; then
    PYTHON_BOOTSTRAP=python
  fi
  "$PYTHON_BOOTSTRAP" -m venv "$VENV_DIR"
fi

if [ -x "$VENV_DIR/bin/python" ]; then
  PYTHON="$VENV_DIR/bin/python"
elif [ -x "$VENV_DIR/Scripts/python.exe" ]; then
  PYTHON="$VENV_DIR/Scripts/python.exe"
else
  echo "Unable to locate python executable in virtual environment" >&2
  exit 1
fi

"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -r requirements.txt

TORCH_SPEC="${PINOKIO_TORCH_SPEC:-torch}"
TRANSFORMERS_SPEC="${PINOKIO_TRANSFORMERS_SPEC:-transformers}"
NEMO_SPEC="${PINOKIO_NEMO_SPEC:-nemo_toolkit[tts]}"
AUDIO_DEPS_SPEC="${PINOKIO_AUDIO_DEPS_SPEC:-librosa soundfile}"

"$PYTHON" -m pip install "$TORCH_SPEC"
"$PYTHON" -m pip install "$TRANSFORMERS_SPEC"
"$PYTHON" -m pip install "$NEMO_SPEC"
# shellcheck disable=SC2086
"$PYTHON" -m pip install $AUDIO_DEPS_SPEC

echo "[pinokio] dependency installation complete"
