# KaniTTS Local Text-to-Speech Service

This project packages the open **KaniTTS** text-to-speech model into a local
service that can be launched with a single command. It provides:

- **Automatic mode** – paste text or upload a document and produce narration in
  a single click.
- **Manual mode** – review the automatically generated segments and render them
  one at a time for fine-grained control (e.g. switch voices between chapters).
- **REST API** – external tools can call `POST /api/synthesize` with text (or a
  document) and receive the generated audio file path and metadata.
- **Voice selection** – choose any of the multi-speaker voices supplied with the
  KaniTTS checkpoint.
- **Chunking for long-form narration** – large inputs are split into manageable
  batches so that books and reports can be generated reliably.

The service runs locally and is optimised for integration with Pinokio's
auto-start scripts, but it can equally be launched from the command line or
containerised for deployment.

---

## 1. Features at a Glance

| Capability | Automatic Mode | Manual Mode | API |
|------------|----------------|-------------|-----|
| Text box input | ✅ | ✅ | ✅ |
| File upload (`.txt`, `.docx`, `.epub`) | ✅ | ✅ | ✅ (via multipart form) |
| Voice selection | ✅ | ✅ | ✅ |
| Advanced sampling controls | ✅ | ✅ | ✅ |
| Batch/segment control | Automatic | User-driven | Automatic |
| Returns audio file path | ✅ | ✅ | ✅ |

---

## 2. Quick Start

1. **Install dependencies** (create a virtual environment first if preferred):

   ```bash
   pip install -r requirements.txt
   ```

   The requirements file lists lightweight tooling for the server and UI. The
   actual KaniTTS runtime depends on `torch`, `transformers`,
   `nemo_toolkit[tts]`, `librosa`, and `soundfile`. These packages are sizeable
   and are therefore not pinned here—install them separately according to your
   platform and GPU support.

2. **Run the server**:

   ```bash
   python -m src.main
   ```

   The service listens on `http://127.0.0.1:8000`. Open `http://127.0.0.1:8000/ui`
   in a browser to use the Gradio interface.

3. **Stop the server** with `Ctrl+C`.

---

## 3. Using the REST API

### `POST /api/synthesize`

Send JSON with either `text` or `file_path` plus optional generation settings.
The server returns the path to the generated WAV file alongside metadata.

```bash
curl -X POST http://127.0.0.1:8000/api/synthesize \
  -H "Content-Type: application/json" \
  -d '{
        "text": "Hello from KaniTTS!",
        "voice": "Jenny (English, Irish)",
        "temperature": 1.4,
        "return_segments": true
      }'
```

Response:

```json
{
  "audio_file": "output/kani_tts_abc123.wav",
  "voice": "Jenny (English, Irish)",
  "segment_count": 1,
  "duration_seconds": 3.7,
  "segments": [
    {"index": 1, "text": "Hello from KaniTTS!", "duration_seconds": 3.7}
  ]
}
```

### `POST /api/synthesize/file`

Use multipart form data to upload a document. The endpoint exposes the same
parameters as the JSON API and returns the same payload shape.

```bash
curl -X POST http://127.0.0.1:8000/api/synthesize/file \
  -F "file=@chapter01.txt" \
  -F "voice=David (English, British)"
```

---

## 4. Automatic vs Manual Modes

- **Automatic mode** (default when the UI loads) will read the text box or the
  uploaded file, split it into segments that fit within the model's token
  limits, run the entire synthesis pipeline, and save the combined waveform as a
  single audio file.

- **Manual mode** lets advanced users inspect the detected segments. After
  clicking *Prepare manual session* you will see an overview table listing each
  segment and its token estimate. Use *Generate next segment* to render the
  narration chunk by chunk—ideal for swapping voices, inserting pauses, or
  checking quality chapter by chapter.

The UI honours the advanced sampling controls (temperature, top-p, repetition
penalty, and max tokens) in both modes, mirroring the parameters exposed via the
API.

---

## 5. Customisation & Pinokio Integration

- **Voices**: the available voices are defined in `src/config.py`. Add or edit
  entries to align with future KaniTTS releases.
- **Chunk sizing**: tweak `DEFAULT_MAX_INPUT_TOKENS` in `src/config.py` if you
  have ample GPU headroom and want larger batches.
- **Pinokio**: create a Pinokio script that runs `python -m src.main`. Because
  the UI defaults to automatic mode, a Pinokio auto-start configuration delivers
  the requested "one-click" experience while still exposing manual controls when
  needed.

---

## 6. Development Notes

- The codebase keeps heavy ML imports lazy to avoid slowing down unit tests or
  environments without GPU support.
- New helper modules include:
  - `src/io_utils.py` – resolves text inputs from direct entry or files.
  - `src/chunking.py` – robust chunk splitting that respects the model's token
    budget.
  - `src/tts_engine.py` – orchestrates token generation and codec decoding.
  - `src/server.py` / `src/ui.py` – FastAPI endpoints and Gradio interface.
- Tests cover the chunking and text-loading helpers so that core behaviour can
  be validated without requiring the heavyweight model downloads.

---

## 7. License

This project inherits the licensing of the original repository. Refer to the
repository's root `LICENSE` file if available. KaniTTS and NanoCodec are subject
to their respective licences—review them on Hugging Face before distribution.
