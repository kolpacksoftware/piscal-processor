"""Tests for piscal_processor.storage (FilesystemBackend)."""

from pathlib import Path

import pandas as pd
import pytest

from piscal_processor.storage import FilesystemBackend, get_backend


def test_get_backend_local_returns_filesystem():
    backend = get_backend("/tmp/foo")
    assert isinstance(backend, FilesystemBackend)


def test_get_backend_s3a_returns_s3_backend():
    try:
        backend = get_backend("s3a://bucket/path")
        assert type(backend).__name__ == "S3Backend"
    except ImportError:
        pytest.skip("s3fs not installed")


def test_filesystem_backend_list_csv_paths(tmp_path):
    (tmp_path / "a.csv").write_text("x")
    (tmp_path / "b.csv").write_text("y")
    (tmp_path / "c.txt").write_text("z")
    backend = FilesystemBackend()
    paths = backend.list_csv_paths(tmp_path)
    assert len(paths) == 2
    assert any("a.csv" in p for p in paths)
    assert any("b.csv" in p for p in paths)


def test_filesystem_backend_read_write_text(tmp_path):
    backend = FilesystemBackend()
    path = tmp_path / "f.txt"
    backend.write_text(path, "hello")
    assert backend.read_text(path) == "hello"
    assert backend.exists(path)


def test_filesystem_backend_stem_name(tmp_path):
    path = tmp_path / "curve_001.csv"
    path.touch()
    backend = FilesystemBackend()
    assert backend.stem(path) == "curve_001"
    assert backend.name(path) == "curve_001.csv"


def test_filesystem_backend_parquet_roundtrip(tmp_path):
    backend = FilesystemBackend()
    path = tmp_path / "out.parquet"
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    backend.write_parquet(df, path)
    out = backend.read_parquet(path)
    pd.testing.assert_frame_equal(out, df)


def test_ensure_output_parent(tmp_path):
    backend = FilesystemBackend()
    path = tmp_path / "sub" / "deep" / "file.csv"
    backend.ensure_output_parent(path)
    assert path.parent.exists()
