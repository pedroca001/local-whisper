# LocalWhisper — Agent Guide

Briefing for AI coding agents working on this repo. Mirrors `CLAUDE.md`.

---

## What it does

Offline dictation app for Windows powered by Whisper / Parakeet on NVIDIA GPUs.

- **Global hotkey** (default `Ctrl+Space`) starts/stops recording from any window.
- **Text injection**: when focus is on a text field, transcribed text is typed there
  via `SendInput` + `KEYEVENTF_UNICODE` (PT-BR accents work).
- **Overlay** appears when focus is on Desktop/Taskbar; result goes to history.
- **System tray** menu: Settings / Record manually / Quit.
- **Settings UI** (PySide6) with pages: Home, Modes, Transcribe File, Vocabulary,
  Configuration, Sound, History.
- **History** for last 7 days, mirrored as `.txt` files per day.
- **Transcribe File** (new): pick mp3/mp4/wav/mkv/etc., choose language (or
  auto-detect), optionally identify speakers via pyannote.audio. Output is plain
  text with `[Speaker N]` tags.
- **Models**: `whisper-turbo` (default), `whisper-ultra` (`large-v3`),
  `parakeet-v3` (lazy via NeMo, optional extra).

---

## Layout

```
run.py                          # Entry point; pythonw redirects + six patch + argparse
install.ps1                     # One-click installer (idempotent)
uninstall.ps1                   # Removes shortcuts only
pyproject.toml                  # Editable install + extras: parakeet, diarize, dev
localwhisper/
  app.py                        # QApplication, tray, hotkey wiring
  audio.py                      # sounddevice Recorder, SAMPLE_RATE=16000
  hotkey.py                     # Global hotkey via Win32 RegisterHotKey
  injector.py                   # SendInput KEYEVENTF_UNICODE typer
  focus.py                      # Detect if focused window has a text field
  config.py                     # JSON config in %APPDATA%\LocalWhisper\config.json
  storage.py                    # SQLite history + .txt mirror
  gpu.py                        # NVML detect + register CUDA DLL dir (torch/lib first)
  autostart.py                  # HKCU\...\Run toggle
  transcriber/
    base.py                     # ASREngine ABC
    registry.py                 # list_models / get_engine
    faster_whisper_engine.py    # ctranslate2-based engines
    parakeet_engine.py          # NeMo lazy import (optional)
    diarization.py              # pyannote.audio Pipeline wrapper
    file_transcriber.py         # ffmpeg → ASR → diarize → stitch
  ui/
    settings_window.py          # Sidebar + page switcher
    style.qss                   # Qt stylesheet
    icons.py                    # SVG icons
    pages/                      # home, modes, transcribe_file, vocabulary,
                                # configuration, sound, history
    widgets/                    # card, waveform, toggle_switch
  resources/icons/              # App + tray icons (also at icons/ at repo root)
tests/                          # pytest, no GUI deps
```

---

## Install / build workflow

**Recommended (source install via GitHub):**

```powershell
git clone https://github.com/pedroca001/local-whisper.git
cd local-whisper
.\install.ps1
```

`install.ps1` is idempotent and:

1. Verifies Python 3.10–3.12.
2. Creates `.venv` if missing.
3. Detects NVIDIA GPU via `nvidia-smi`. Picks the right PyTorch index:
   - RTX 50xx / Blackwell → `cu128`
   - Others NVIDIA → `cu121`
   - No NVIDIA → `cpu`
   Override with `-CudaIndex <url>` or `-ForceCpu`.
4. Installs torch + torchaudio if missing (detected via `Test-Path` on the
   package dir; do NOT shell out — see "PowerShell 5.1 quirks" below).
5. `pip install -e .[diarize]` — editable + diarization extra.
6. Smoke test (informational; failure is non-fatal).
7. Creates `LocalWhisper.lnk` on Desktop and in `%APPDATA%\Microsoft\Windows\
   Start Menu\Programs\Startup`. Skip with `-NoShortcut` / `-NoStartup`.

**Manual install** documented in `README.md`.

**`.exe` build** still works via `build.ps1` + `installer.iss` (PyInstaller +
Inno Setup), but **diarization will not work in the bundled `.exe`** because
`localwhisper.spec` excludes `torch`/`torchaudio` to keep the bundle small.
Source install is the supported path.

---

## Known bugs / quirks

### PowerShell 5.1 (Windows PowerShell)

- **Native-command stderr wrapping**: `& exe ... 2>$null` (or `2>&1`) wraps each
  stderr line as `NativeCommandError`; under `$ErrorActionPreference = "Stop"`
  this aborts the script even on exit code 0. Avoid stderr redirects on native
  commands. For "is package installed" probes, use `Test-Path` on
  `.venv\Lib\site-packages\<pkg>\__init__.py`.
- **ANSI script encoding**: `.ps1` files without a UTF-8 BOM are read as
  Windows-1252. Non-ASCII characters cause parse errors. Keep all scripts ASCII.
- **`$Args` is reserved**: never use `$Args` as a function param name — it
  silently fails to bind. Use `$ArgList` or anything else.

### `pythonw.exe` silent crash

Under `pythonw.exe`, `sys.stdout` and `sys.stderr` are `None`. Any module that
prints or writes a warning during import raises `AttributeError` and the app
crashes silently. `run.py` redirects to log files in
`%LOCALAPPDATA%\LocalWhisper\app.log` / `app.log.err` *before* any other
imports. **Do not move that block.**

### PySide6 + `six` import-hook crash

`pystray._win32` does `from six.moves import queue`. PySide6's
`shibokensupport.feature.feature_imported` introspects every newly imported
module with `inspect.getsource()`, which calls `repr()` on `six.moves`
submodules. CPython's `_module_repr_from_spec` reads `spec.loader._path`, but
six's `_SixMetaPathImporter` has no `_path` attribute → `AttributeError`,
import chain dies, app fails to start.

**Fix in `run.py`** (do not remove): we patch
`six._SixMetaPathImporter._path = None` early, before PySide6 is loaded.

Symptom on broken machines: `AttributeError: '_SixMetaPathImporter' object has
no attribute '_path'` in `app.log.err`. The condition depends on PySide6 / six
versions, so it appears on some PCs and not others.

### `torchcodec` warning at import

`pyannote.audio` pulls in `torchcodec`, which tries to load FFmpeg system DLLs.
We don't ship those — but we never need torchcodec because
`localwhisper/transcriber/diarization.py` feeds the pipeline a preloaded
`{"waveform": tensor, "sample_rate": int}` dict (decoded by `imageio-ffmpeg`).
The warning at import time is **cosmetic, ignore it.**

### CUDA detection

`localwhisper/gpu.py` checks for a loadable `cublas64_12.dll` in this order:
already in PATH → frozen `_MEIPASS` → `torch/lib/` (the wheel-bundled CUDA
runtime) → `CUDA_PATH` env vars → standard CUDA Toolkit install dir.

The `torch/lib/` step is what makes GPU work without a system-wide CUDA Toolkit
install. If you change torch versions and lose `cublas64_12.dll`, GPU silently
falls back to CPU; check `app.log` for `"Registered torch CUDA lib dir"` /
`"cublas64_12.dll found in torch wheel"`.

### Diarization requires HuggingFace token

`pyannote/speaker-diarization-3.1` is gated. User must:
1. Accept terms at <https://huggingface.co/pyannote/speaker-diarization-3.1>.
2. Generate a Read token at <https://huggingface.co/settings/tokens>.
3. Paste into Settings → Configuration → HuggingFace token.

Without a token, file transcription still works — only the speaker labels are
skipped. Error path is in `transcriber/diarization.py`.

### `pyproject.toml` Python cap

Says `>=3.10,<3.13` but the dev `.venv` may already be on 3.12 or even 3.14.
Most code works on 3.13/3.14 but PyTorch wheel availability varies. If you
bump, verify `cu128` wheels exist for the target Python version before
relaxing the cap.

### `.exe` bundle gap

`localwhisper.spec` excludes `torch`/`torchaudio` (they were only used by the
optional Parakeet path). After adding diarization, the bundle no longer
supports speaker ID. Either:
- Drop `.exe` distribution (current direction — see commit 87800d2).
- Or remove `torch`/`torchaudio` from `excludes` and add `pyannote.audio` to
  `collect_all`. Bundle grows by ~3 GB.

---

## Conventions

- Use `Edit` over `Write` for existing files; never reformat unrelated code.
- Keep `.ps1` scripts ASCII-only (see PowerShell 5.1 quirks).
- New deps go in `pyproject.toml` (and `requirements.txt` mirror).
- New optional features → an `[extras]` group, not core deps.
- Lazy-import heavy modules (`torch`, `pyannote.audio`, `nemo`) inside the
  function that needs them, not at module top.
- Don't print directly — use `logging.getLogger(__name__)`.
- Tests in `tests/` must not import PySide6 or run the GUI.

---

## Useful commands

```powershell
# Run from source (with console for debugging)
.\.venv\Scripts\python.exe run.py

# Run hidden (production)
.\.venv\Scripts\pythonw.exe run.py

# Tail crash log
Get-Content "$env:LOCALAPPDATA\LocalWhisper\app.log.err" -Tail 80

# CLI test (no UI, no tray)
.\.venv\Scripts\python.exe run.py --cli --duration 5 --model whisper-turbo

# List models
.\.venv\Scripts\python.exe run.py --list-models

# Tests
.\.venv\Scripts\python.exe -m pytest tests/

# Inspect shortcut
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut("$env:USERPROFILE\Desktop\LocalWhisper.lnk")
$lnk | Format-List Target*, Arguments, WorkingDirectory, IconLocation
```

---

## File system surfaces

- Config: `%APPDATA%\LocalWhisper\config.json`
- History DB: `%APPDATA%\LocalWhisper\history.db`
- Logs: `%LOCALAPPDATA%\LocalWhisper\app.log`, `app.log.err`
- Whisper model cache: `%LOCALAPPDATA%\LocalWhisper\models`
- HuggingFace cache (pyannote weights ~70 MB): `%USERPROFILE%\.cache\huggingface`
- User-visible transcripts: `%USERPROFILE%\Documents\LocalWhisper` (configurable)
