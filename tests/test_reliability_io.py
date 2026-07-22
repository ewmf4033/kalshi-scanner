from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.reliability_io import (
    atomic_write_json,
    build_daily_manifest,
    immutable_write_bytes,
    immutable_write_json,
    sha256_bytes,
)


def test_atomic_write_json_produces_valid_complete_json(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    atomic_write_json(path, {"status": "ended", "count": 3})
    assert json.loads(path.read_text()) == {"status": "ended", "count": 3}
    assert not list(tmp_path.glob(".state.json.*"))


def test_immutable_write_is_idempotent_for_identical_bytes(tmp_path: Path) -> None:
    path = tmp_path / "raw.ndjson"
    payload = b'{"custom_id":"test"}\n'
    first = immutable_write_bytes(path, payload)
    second = immutable_write_bytes(path, payload)
    assert first == second == sha256_bytes(payload)
    assert path.read_bytes() == payload


def test_immutable_write_refuses_different_replacement(tmp_path: Path) -> None:
    path = tmp_path / "forecast.json"
    immutable_write_json(path, {"gap": True})
    with pytest.raises(FileExistsError, match="immutable artifact"):
        immutable_write_json(path, {"gap": False})
    assert json.loads(path.read_text()) == {"gap": True}


def test_manifest_contains_hashes_not_file_contents(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.json"
    output = tmp_path / "scan.json"
    snapshot.write_text('[{"ticker":"TEST","implied_prob":0.4}]')
    output.write_text('{"probability":0.9,"direction":"YES"}')

    manifest = build_daily_manifest(
        date="2026-07-22",
        snapshot_path=snapshot,
        output_paths=[output],
        code_commit="abc123",
        no_search_enforced=True,
    )

    serialized = json.dumps(manifest)
    assert manifest["gap_retry_supported"] is False
    assert manifest["outputs"][str(output)]["sha256"]
    assert "probability" not in serialized
    assert "direction" not in serialized
    assert "YES" not in serialized
