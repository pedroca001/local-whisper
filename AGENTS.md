# LocalWhisper - Agent Guide

## Purpose

- Source repo for Pedro's Windows offline dictation and transcription app.
- The canonical source checkout is `<CODIGO_ROOT>\LocalWhisper`; the Brain context lives in `<BRAIN_ROOT>\Projetos\Webapps_Infoapps\localwhisper.md`.
- The app records audio locally, transcribes with Whisper/Parakeet on NVIDIA GPUs, and inserts text into the focused Windows target.

## Ownership

- Brain owner doc: `<BRAIN_ROOT>\Projetos\Webapps_Infoapps\localwhisper.md`.
- Code inventory: `<BRAIN_ROOT>\REFERENCIAS_CODIGO.md`.
- Current desktop runtime venv: `%LOCALAPPDATA%\LocalWhisper\venv`, installed with `.\install.ps1 -VenvPath "$env:LOCALAPPDATA\LocalWhisper\venv"`.
- Model cache: `%LOCALAPPDATA%\LocalWhisper\models`. Do not move or delete the `large-v3-turbo` / `whisper-turbo` cache without explicit approval from Pedro.

## Local Contracts

- Supported distribution is source install. The `.exe` build path is secondary and does not support diarization unless the PyInstaller bundle is redesigned.
- Keep heavy runtime artifacts out of Git. `.venv`, logs, build output, downloaded models, caches, and local credentials stay untracked.
- Keep the early stdout/stderr redirect and `six` import hook patch in `run.py`; moving them can make `pythonw.exe` fail silently.
- Text insertion must preserve the validated cascade: direct Win32/RichEdit insertion, Unicode `SendInput` fallback, then protected clipboard paste only for modern browser/Electron-style targets.
- Clipboard snapshots must only call `GlobalSize`/`GlobalLock` for `HGLOBAL`-backed formats. Never treat `CF_BITMAP`, palette, or metafile handles as global memory; preserve bitmap content through `CF_DIB`/`CF_DIBV5`.
- Config and history live in `%APPDATA%\LocalWhisper`; logs and models live in `%LOCALAPPDATA%\LocalWhisper`.
- HuggingFace tokens for pyannote are user secrets stored with Windows DPAPI.
  Never write token values to the repo, Brain, logs, config JSON, or chat.
- Dictation must use the explicit session state machine. Do not allow a second
  recording while finalization or insertion is still in progress.
- Streaming may only inject stable consensus prefixes. If the final hypothesis
  diverges, use the recovery overlay rather than appending a corrupt suffix.
- Keep partial inference throttled; never run Whisper once per 30 ms audio block.

## Work Guidance

- Use `install.ps1` for setup and updates. For synced source folders, pass `-VenvPath "$env:LOCALAPPDATA\LocalWhisper\venv"` so the heavy Python runtime does not live in Google Drive.
- Keep `.ps1` scripts ASCII-safe for Windows PowerShell 5.1.
- Add dependencies in `pyproject.toml`; mirror only when the existing requirements workflow needs it.
- Lazy-import heavy modules such as `torch`, `pyannote.audio`, and `nemo` inside the feature path that needs them.
- Tests in `tests/` should not import PySide6 or require the GUI/tray.
- For insertion changes, verify a native target such as Notepad separately from browser/Electron editors.

## Verification

- Install/update on Pedro's desktop:
  ```powershell
  .\install.ps1 -VenvPath "$env:LOCALAPPDATA\LocalWhisper\venv"
  ```
- Confirm editable install points to this repo:
  ```powershell
  & "$env:LOCALAPPDATA\LocalWhisper\venv\Scripts\python.exe" -m pip show localwhisper
  ```
- Smoke imports and model listing:
  ```powershell
  & "$env:LOCALAPPDATA\LocalWhisper\venv\Scripts\python.exe" run.py --list-models
  ```
- Run non-GUI tests:
  ```powershell
  & "$env:LOCALAPPDATA\LocalWhisper\venv\Scripts\python.exe" -m pytest tests/
  ```
- Verify CLI wrapper and model cache:
  ```powershell
  whisper --check
  whisper --model-path
  ```
- Inspect Desktop/Startup shortcuts after installer changes; both should target `%LOCALAPPDATA%\LocalWhisper\venv\Scripts\pythonw.exe` with `run.py` from `<CODIGO_ROOT>\LocalWhisper`.

## Child DOX Index

- `localwhisper/`: application package, CLI, session state, diagnostics, DPAPI
  secrets, transcription engines, UI, text insertion, storage, config, hotkey,
  tray, and assets.
- `localwhisper/transcriber/`: ASR backends, diarization, file transcription, and model registry.
- `localwhisper/ui/`: PySide6 settings UI, overlay, pages, widgets, icons, and styling.
- `tests/`: non-GUI pytest coverage for storage, vocabulary, hotkeys, insertion policy, injector behavior, model manager, assets, and audio gate logic.
- `tools/`: manual verification helpers such as real Windows text insertion target checks.
- `icons/` and `localwhisper/resources/`: app and tray icon sources used by shortcuts and builds.
