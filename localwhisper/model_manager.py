from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from huggingface_hub import snapshot_download

from .transcriber.registry import list_models


@dataclass(frozen=True)
class ModelStatus:
    key: str
    display_name: str
    subtitle: str
    installed: bool
    active: bool
    installable: bool
    cache_kind: str
    cache_path: str
    note: str = ""


def _hf_cache_dir(models_dir: str | Path, repo_id: str) -> Path:
    safe = "models--" + repo_id.replace("/", "--")
    return Path(models_dir) / safe


def _model_cache_path(models_dir: str | Path, meta: dict) -> Path:
    if meta.get("cache_kind") == "huggingface":
        return _hf_cache_dir(models_dir, meta["repo_id"])
    return Path(models_dir) / meta.get("cache_subdir", meta["key"])


def _has_hf_snapshot(cache_path: Path) -> bool:
    if not cache_path.exists():
        return False
    refs_main = cache_path / "refs" / "main"
    snapshots = cache_path / "snapshots"
    if refs_main.exists():
        return True
    if snapshots.exists() and any(snapshots.iterdir()):
        return True
    return any(cache_path.iterdir())


def list_model_status(models_dir: str | Path, active_key: str) -> list[ModelStatus]:
    Path(models_dir).mkdir(parents=True, exist_ok=True)
    statuses: list[ModelStatus] = []
    for meta in list_models():
        cache_path = _model_cache_path(models_dir, meta)
        cache_kind = meta.get("cache_kind", "unknown")
        installable = bool(meta.get("installable", True))
        installed = _has_hf_snapshot(cache_path) if cache_kind == "huggingface" else cache_path.exists()
        if meta["key"] == active_key and cache_kind == "huggingface":
            installed = installed or cache_path.exists()
        note = ""
        if cache_kind == "nemo":
            note = "Requires the optional Parakeet/NeMo dependency; install prepares the model after that dependency exists."
        statuses.append(
            ModelStatus(
                key=meta["key"],
                display_name=meta["display_name"],
                subtitle=meta.get("subtitle", ""),
                installed=installed,
                active=meta["key"] == active_key,
                installable=installable,
                cache_kind=cache_kind,
                cache_path=str(cache_path),
                note=note,
            )
        )
    return statuses


def install_model(key: str, models_dir: str | Path) -> None:
    meta = next((m for m in list_models() if m["key"] == key), None)
    if meta is None:
        raise KeyError(f"Unknown model: {key}")
    Path(models_dir).mkdir(parents=True, exist_ok=True)
    if meta.get("cache_kind") == "huggingface":
        snapshot_download(repo_id=meta["repo_id"], cache_dir=str(models_dir))
        return
    if meta.get("cache_kind") == "nemo":
        from nemo.collections.asr.models import ASRModel

        ASRModel.from_pretrained(meta["repo_id"])
        return
    raise RuntimeError(f"Model {key} does not support installation from the app.")


def uninstall_model(key: str, models_dir: str | Path, active_key: str) -> None:
    if key == active_key:
        raise RuntimeError("Switch to another model before uninstalling the active model.")
    meta = next((m for m in list_models() if m["key"] == key), None)
    if meta is None:
        raise KeyError(f"Unknown model: {key}")
    path = _model_cache_path(models_dir, meta).resolve()
    root = Path(models_dir).resolve()
    if root not in path.parents:
        raise RuntimeError("Refusing to remove a model outside the configured models folder.")
    if path.exists():
        shutil.rmtree(path)
