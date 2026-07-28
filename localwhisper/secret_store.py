"""Small Windows Credential Protection wrapper for LocalWhisper secrets.

Secrets are encrypted with Windows DPAPI for the current user before they are
written to disk.  This keeps tokens out of config.json without adding a heavy
runtime dependency or requiring an online account.
"""
from __future__ import annotations

import base64
import ctypes
import json
import logging
import os
import sys
from ctypes import wintypes
from pathlib import Path

log = logging.getLogger(__name__)

_CRYPTPROTECT_UI_FORBIDDEN = 0x1


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _blob(data: bytes) -> tuple[_DATA_BLOB, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    value = _DATA_BLOB(
        len(data),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    return value, buffer


def _protect(data: bytes) -> bytes:
    if sys.platform != "win32":
        raise OSError("Windows DPAPI is only available on Windows")
    source, source_buffer = _blob(data)
    result = _DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptProtectData(
        ctypes.byref(source),
        "LocalWhisper secret",
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(result),
    )
    del source_buffer
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(result.pbData)


def _unprotect(data: bytes) -> bytes:
    if sys.platform != "win32":
        raise OSError("Windows DPAPI is only available on Windows")
    source, source_buffer = _blob(data)
    result = _DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(result),
    )
    del source_buffer
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(result.pbData)


class SecretStore:
    """Encrypted JSON-backed secret store scoped to the current Windows user."""

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except Exception:
            log.exception("Could not read encrypted secret store")
            return {}

    def _write(self, data: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(
            json.dumps(data, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temp, self.path)

    def get(self, key: str, default: str = "") -> str:
        encoded = self._read().get(key)
        if not encoded:
            return default
        try:
            protected = base64.b64decode(encoded.encode("ascii"), validate=True)
            return _unprotect(protected).decode("utf-8")
        except Exception:
            log.exception("Could not decrypt secret %r", key)
            return default

    def set(self, key: str, value: str) -> None:
        data = self._read()
        if not value:
            if key in data:
                del data[key]
                self._write(data)
            return
        protected = _protect(value.encode("utf-8"))
        data[key] = base64.b64encode(protected).decode("ascii")
        self._write(data)
