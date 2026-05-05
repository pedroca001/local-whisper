# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Full collection for packages with native binaries / dynamic imports.
# collect_all() gathers hiddenimports, binaries AND data from each package.
datas = []
binaries = []
hiddenimports = []

for pkg in ('ctranslate2', 'faster_whisper', 'onnxruntime', 'huggingface_hub', 'sounddevice'):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:
        print(f'Warning: could not collect {pkg}: {e}')

# Bundle minimal CUDA 12 runtime DLLs so GPU works on any NVIDIA GPU without
# requiring the user to install the CUDA Toolkit separately.
# We ship cublas64_12.dll + cudart64_12.dll from torch's bundled CUDA.
# cublasLt64_12.dll (644 MB) is intentionally skipped — ctranslate2 loads it
# optionally and falls back to regular cuBLAS when it is absent.
# Users who have the full CUDA Toolkit installed get cublasLt automatically.
import os as _os
from pathlib import Path as _Path

def _find_cuda_dll(dll_name: str) -> str | None:
    """Find a CUDA 12 DLL in common locations."""
    # 1. torch bundled CUDA (present in the venv used to build)
    _candidates = [
        _Path('.venv/Lib/site-packages/torch/lib') / dll_name,
    ]
    # 2. CUDA Toolkit environment variables
    for _var in ('CUDA_PATH', 'CUDA_PATH_V12_0', 'CUDA_HOME'):
        _val = _os.environ.get(_var)
        if _val:
            _candidates.append(_Path(_val) / 'bin' / dll_name)
    # 3. Standard CUDA Toolkit install locations
    _base = _Path('C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA')
    if _base.is_dir():
        for _vdir in sorted(_base.iterdir(), key=lambda p: p.name, reverse=True):
            if _vdir.name.startswith('v12'):
                _candidates.append(_vdir / 'bin' / dll_name)
    for _p in _candidates:
        if _p.exists():
            print(f'  Bundling CUDA DLL: {_p}')
            return str(_p)
    print(f'  Warning: {dll_name} not found — GPU may fall back to CPU')
    return None

for _dll in ('cublas64_12.dll', 'cublasLt64_12.dll', 'cudart64_12.dll'):
    _src = _find_cuda_dll(_dll)
    if _src:
        binaries += [(_src, '.')]

# Additional hidden imports that static analysis misses
hiddenimports += [
    # pystray Windows backend (loaded dynamically based on platform)
    'pystray._win32',
    'pystray._util',
    # scipy submodules used by faster-whisper
    'scipy.signal',
    'scipy.io',
    'scipy.io.wavfile',
    'scipy.fft',
    # stdlib modules that PyInstaller sometimes misses in windowed mode
    'winreg',
    'wave',
]

# App-specific data files
datas += [
    # Icons: placed at _MEIPASS/icons/ — matches assets.py frozen-mode lookup
    ('localwhisper/resources/icons', 'icons'),
    # Qt stylesheet: loaded via Path(__file__).parent / "style.qss" in settings_window.py
    ('localwhisper/ui/style.qss', 'localwhisper/ui'),
]

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude Parakeet/torch — lazy-loaded, not needed for Whisper models
        'torch', 'torchaudio', 'torchvision',
        'nemo', 'nemo_toolkit',
        # Exclude unused heavy packages
        'IPython', 'jupyter', 'matplotlib', 'tkinter',
        'unittest', 'pydoc', 'doctest',
        'pandas', 'sklearn', 'sympy',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# collect_all('ctranslate2') may also pull in CUDA DLLs via dependency analysis,
# placing them in subdirs like torch/lib/.  Remove those subdir copies — our
# explicit bundling above already placed the correct versions at _internal/ root.
_cuda_dlls_at_root = {'cublas64_12.dll', 'cublaslt64_12.dll', 'cudart64_12.dll'}
a.binaries = TOC([
    (name, path, typecode)
    for name, path, typecode in a.binaries
    if not (
        _os.path.basename(name.replace('\\', '/')).lower() in _cuda_dlls_at_root
        and _os.path.dirname(name.replace('\\', '/'))  # has a subdir component
    )
])

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LocalWhisper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX can corrupt DLLs from ctranslate2/onnxruntime
    console=False,      # Windowed app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='localwhisper/resources/icons/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='LocalWhisper',
)
