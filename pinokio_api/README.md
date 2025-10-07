# Pinokio Drop-In Package

This folder bundles everything Pinokio needs so you can drag the project into
`~/Pinokio/api` (or the equivalent folder on your platform) and launch the
service without additional wiring.

## Files

- `pinokio.json` – describes the install/run actions so Pinokio can show one
  click buttons.
- `install.sh` – creates an isolated Python virtual environment (defaults to
  `.venv`) and installs the runtime dependencies. You can override the Torch,
  Transformers, NeMo, and audio packages by supplying environment variables (see
  below).
- `start.sh` – activates the same virtual environment and runs the FastAPI /
  Gradio server via `python -m src.main`.

Both shell scripts run from the repository root so relative paths in the codebase
continue to work as expected.

## Usage

1. Copy or drag this repository into Pinokio's `api` workspace directory. The
   folder should appear in the Pinokio UI as an app named **KaniTTS Local TTS**.
2. Open the app in Pinokio and click **Install dependencies**. This runs
   `pinokio_api/install.sh` and will download the Python packages into `.venv`.
   - Set optional environment variables if you need custom wheels:
     - `PINOKIO_TORCH_SPEC` – e.g. `torch==2.3.1+cu121 --index-url https://download.pytorch.org/whl/cu121`
     - `PINOKIO_TRANSFORMERS_SPEC`
     - `PINOKIO_NEMO_SPEC`
     - `PINOKIO_AUDIO_DEPS_SPEC`
     - `PINOKIO_PYTHON_BIN` – bootstrap interpreter for creating the virtual environment.
     - `PINOKIO_VENV_DIR` – change the venv location if `.venv` is unsuitable.
3. Once installation completes, click **Start service** (or enable auto-start).
   Pinokio runs `pinokio_api/start.sh`, which launches the server on
   `http://127.0.0.1:8000` and exposes the UI at `/ui`.

The UI loads in automatic mode by default. Switch to manual mode to walk through
segments one at a time or adjust the advanced sampling controls before
synthesising.

## Manual invocation

If you prefer running outside Pinokio, execute the scripts directly:

```bash
bash pinokio_api/install.sh
bash pinokio_api/start.sh
```

They are safe to run multiple times; the installer simply reuses the existing
virtual environment if one already exists.
