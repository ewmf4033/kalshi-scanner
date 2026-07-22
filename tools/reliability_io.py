#!/usr/bin/env python3
"""Methodologically neutral reliability helpers for the shadow experiment.

This module does not alter prompts, models, thresholds, market eligibility,
selection rules, or outcome handling. It only provides safer persistence,
locking, hashing, and metadata-manifest primitives.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write_bytes(path: Path, payload: bytes, *, mode: int = 0o644) -> None:
    """Atomically replace a non-final metadata file on the same filesystem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
        dir_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def atomic_write_json(path: Path, data: Any) -> None:
    payload = (json.dumps(data, indent=2, sort_keys=False) + "\n").encode("utf-8")
    atomic_write_bytes(path, payload)


def immutable_write_bytes(path: Path, payload: bytes, *, mode: int = 0o444) -> str:
    """Create an immutable-by-policy artifact and refuse all replacement.

    Returns the SHA-256 of the written bytes. Existing files are accepted only
    when their bytes are identical, making repeated calls idempotent.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = sha256_bytes(payload)
    if path.exists():
        existing = path.read_bytes()
        if existing != payload:
            raise FileExistsError(f"Refusing to replace immutable artifact: {path}")
        return digest

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise
    return digest


def immutable_write_text(path: Path, text: str) -> str:
    return immutable_write_bytes(path, text.encode("utf-8"))


def immutable_write_json(path: Path, data: Any) -> str:
    payload = (json.dumps(data, indent=2, sort_keys=False) + "\n").encode("utf-8")
    return immutable_write_bytes(path, payload)


@contextmanager
def exclusive_lock(lock_path: Path, *, nonblocking: bool = True) -> Iterator[None]:
    """Hold an advisory process lock for the duration of a run."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as handle:
        flags = fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0)
        try:
            fcntl.flock(handle.fileno(), flags)
        except BlockingIOError as exc:
            raise RuntimeError(f"Another experiment process holds lock: {lock_path}") from exc
        try:
            handle.seek(0)
            handle.truncate()
            handle.write(f"pid={os.getpid()} acquired_at={utc_now_iso()}\n")
            handle.flush()
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def build_daily_manifest(
    *,
    date: str,
    snapshot_path: Path,
    output_paths: list[Path],
    code_commit: str,
    no_search_enforced: bool,
) -> dict[str, Any]:
    """Create metadata-only hashes; never reads or summarizes outcomes."""
    files: dict[str, dict[str, Any]] = {}
    for path in sorted(output_paths, key=lambda p: str(p)):
        if not path.exists():
            continue
        files[str(path)] = {
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }

    return {
        "manifest_version": 1,
        "date": date,
        "created_at": utc_now_iso(),
        "code_commit": code_commit,
        "no_search_enforced": bool(no_search_enforced),
        "gap_retry_supported": False,
        "snapshot": {
            "path": str(snapshot_path),
            "sha256": sha256_file(snapshot_path),
            "size_bytes": snapshot_path.stat().st_size,
        },
        "outputs": files,
    }
