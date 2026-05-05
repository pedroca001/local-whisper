"""GPU detection and CUDA runtime setup.

Detects NVIDIA GPUs via nvml.dll (ships with every NVIDIA display driver —
no CUDA Toolkit required). Finds the CUDA 12 Toolkit DLL directory and registers
it so ctranslate2 can load cuBLAS for GPU-accelerated inference.

Call setup() once at application startup, before ctranslate2 is imported.
Afterwards, get_info() returns the cached result from anywhere in the app.
"""
from __future__ import annotations

import ctypes
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

CUDA_TOOLKIT_URL = "https://developer.nvidia.com/cuda-downloads"


@dataclass
class GpuInfo:
    name: str
    vram_gb: float
    cuda_ready: bool  # True when cublas64_12.dll is loadable

    @property
    def vram_label(self) -> str:
        return f"{round(self.vram_gb)} GB"


_info: GpuInfo | None = None
_detected = False


def setup() -> GpuInfo | None:
    """Detect GPU and register CUDA DLL path. Call once before ctranslate2 is imported."""
    global _info, _detected
    if _detected:
        return _info
    _detected = True

    nvml_result = _detect_nvidia()
    if nvml_result is None:
        logger.info("No NVIDIA GPU detected")
        return None

    name, vram_gb = nvml_result
    logger.info("NVIDIA GPU detected: %s  VRAM: %.1f GB", name, vram_gb)

    cuda_ready = _try_register_cuda_12()
    _info = GpuInfo(name=name, vram_gb=vram_gb, cuda_ready=cuda_ready)
    return _info


def get_info() -> GpuInfo | None:
    """Return cached GpuInfo. Returns None if setup() hasn't run or no NVIDIA GPU."""
    return _info


# ── NVIDIA detection via NVML ─────────────────────────────────────────────────

def _detect_nvidia() -> tuple[str, float] | None:
    """Return (gpu_name, vram_gb) for the first device using nvml.dll.

    nvml.dll ships with every NVIDIA display driver, even on machines without
    CUDA Toolkit installed, so this works on old gaming laptops too.
    """
    try:
        nvml = ctypes.WinDLL("nvml.dll")
    except Exception:
        return None

    try:
        if nvml.nvmlInit_v2() != 0:
            return None

        handle = ctypes.c_void_p()
        if nvml.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(handle)) != 0:
            nvml.nvmlShutdown()
            return None

        name_buf = ctypes.create_string_buffer(96)
        nvml.nvmlDeviceGetName(handle, name_buf, ctypes.c_uint(96))
        name = name_buf.value.decode("utf-8", errors="replace").strip()

        class _Mem(ctypes.Structure):
            _fields_ = [
                ("total", ctypes.c_ulonglong),
                ("free",  ctypes.c_ulonglong),
                ("used",  ctypes.c_ulonglong),
            ]

        mem = _Mem()
        nvml.nvmlDeviceGetMemoryInfo(handle, ctypes.byref(mem))
        nvml.nvmlShutdown()
        return name, mem.total / (1024 ** 3)

    except Exception as exc:
        logger.debug("nvml query failed: %s", exc)
        try:
            nvml.nvmlShutdown()
        except Exception:
            pass
        return None


# ── CUDA Toolkit DLL registration ─────────────────────────────────────────────

def _try_register_cuda_12() -> bool:
    """Make cublas64_12.dll loadable and return True if successful.

    Checks (in order):
    1. Already loadable (CUDA Toolkit in system PATH)
    2. Frozen bundle: _MEIPASS contains bundled cublas64_12.dll — register it
       so ctypes.WinDLL (which uses LOAD_LIBRARY_SEARCH_DEFAULT_DIRS and only
       respects AddDllDirectory, not the bootloader's SetDllDirectory) can
       find it too.
    3. Found via CUDA_PATH env var set by the official CUDA installer
    4. Found by scanning the standard CUDA Toolkit install directory
    """
    import sys
    if _cublas_loadable():
        logger.info("cublas64_12.dll already in search path")
        return True

    # In a frozen PyInstaller app the bootloader calls SetDllDirectory(_MEIPASS)
    # so that native C code can find bundled DLLs.  Python's ctypes.WinDLL uses
    # LoadLibraryExW with LOAD_LIBRARY_SEARCH_DEFAULT_DIRS which only searches
    # directories registered via AddDllDirectory.  Bridging that gap here lets
    # _cublas_loadable() succeed for the bundled cublas64_12.dll.
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        try:
            os.add_dll_directory(sys._MEIPASS)
            logger.info("Registered frozen _MEIPASS for DLL search: %s", sys._MEIPASS)
        except Exception as exc:
            logger.debug("add_dll_directory(_MEIPASS) failed: %s", exc)
        if _cublas_loadable():
            logger.info("cublas64_12.dll found in frozen bundle")
            return True

    cuda_bin = _find_cuda_12_bin()
    if cuda_bin is None:
        logger.info("CUDA Toolkit 12 not found — GPU acceleration unavailable")
        return False

    try:
        os.add_dll_directory(str(cuda_bin))
        logger.info("Registered CUDA 12 bin: %s", cuda_bin)
    except Exception as exc:
        logger.warning("os.add_dll_directory failed: %s", exc)
        return False

    if _cublas_loadable():
        return True

    logger.warning("cublas64_12.dll still not loadable after registering %s", cuda_bin)
    return False


def _cublas_loadable() -> bool:
    try:
        ctypes.WinDLL("cublas64_12.dll")
        return True
    except Exception:
        return False


def _find_cuda_12_bin() -> Path | None:
    """Return the bin/ directory of the highest CUDA 12.x Toolkit found, or None."""
    candidates: list[Path] = []

    # Environment variables set by the official CUDA Toolkit installer
    for var in ("CUDA_PATH", "CUDA_PATH_V12_0", "CUDA_HOME"):
        val = os.environ.get(var)
        if val:
            b = Path(val) / "bin"
            if (b / "cublas64_12.dll").exists():
                candidates.append(b)

    # Standard install location — scan for any v12.x sub-directory
    base = Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA")
    if base.is_dir():
        for version_dir in base.iterdir():
            if version_dir.name.startswith("v12"):
                b = version_dir / "bin"
                if (b / "cublas64_12.dll").exists():
                    candidates.append(b)

    if not candidates:
        return None

    # Highest version wins (v12.8 > v12.2 > v12.0, alphabetic sort works)
    return sorted(candidates, key=lambda p: p.parent.name, reverse=True)[0]
