"""
Storage abstraction for PISCAL pipeline I/O.

Provides a backend-agnostic interface for listing, reading, and writing
files so that scripts can use S3/S3A object storage (e.g. in JupyterHub)
or local filesystem without code changes. S3Backend uses fsspec/s3fs for s3a.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, Union

if TYPE_CHECKING:
    import pandas as pd


class StorageBackend(Protocol):
    """Protocol for storage backends (filesystem, S3, etc.)."""

    def list_csv_paths(self, location: Union[str, Path]) -> list[str]:
        """Return sorted list of CSV file paths or URIs under location."""
        ...

    def read_text(
        self,
        uri: Union[str, Path],
        *,
        encoding: str = "utf-8",
        fallback_encoding: Union[str, None] = "iso-8859-1",
    ) -> str:
        """Read file content as text, with optional encoding fallback."""
        ...

    def read_parquet(self, uri: Union[str, Path]) -> Any:
        """Read a Parquet file into a DataFrame."""
        ...

    def write_parquet(self, df: Any, uri: Union[str, Path]) -> None:
        """Write a DataFrame to Parquet format."""
        ...

    def write_text(self, uri: Union[str, Path], content: str) -> None:
        """Write text content to a file."""
        ...

    def exists(self, uri: Union[str, Path]) -> bool:
        """Return True if the path or object exists."""
        ...

    def ensure_output_parent(self, uri: Union[str, Path]) -> None:
        """Ensure the parent directory exists (no-op for object storage)."""
        ...

    def stem(self, uri: Union[str, Path]) -> str:
        """Return filename without extension (for curve_id)."""
        ...

    def name(self, uri: Union[str, Path]) -> str:
        """Return filename with extension (for source_file)."""
        ...


class FilesystemBackend:
    """Storage backend using the local filesystem."""

    def list_csv_paths(self, location: Union[str, Path]) -> list[str]:
        paths = sorted(Path(location).rglob("*.csv"))
        return [str(p) for p in paths]

    def read_text(
        self,
        uri: Union[str, Path],
        *,
        encoding: str = "utf-8",
        fallback_encoding: Union[str, None] = "iso-8859-1",
    ) -> str:
        path = Path(uri)
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            if fallback_encoding is None:
                raise
            return path.read_text(encoding=fallback_encoding)

    def read_parquet(self, uri: Union[str, Path]) -> Any:
        import pandas as pd

        return pd.read_parquet(uri)

    def write_parquet(self, df: Any, uri: Union[str, Path]) -> None:
        df.to_parquet(uri, index=False)

    def write_text(self, uri: Union[str, Path], content: str) -> None:
        # Encoding is pinned so output does not depend on the machine's locale.
        Path(uri).write_text(content, encoding="utf-8")

    def exists(self, uri: Union[str, Path]) -> bool:
        return Path(uri).exists()

    def ensure_output_parent(self, uri: Union[str, Path]) -> None:
        Path(uri).parent.mkdir(parents=True, exist_ok=True)

    def stem(self, uri: Union[str, Path]) -> str:
        return Path(uri).stem

    def name(self, uri: Union[str, Path]) -> str:
        return Path(uri).name


class S3Backend:
    """Storage backend using S3-compatible storage (MinIO, AWS S3) via fsspec/s3fs."""

    def __init__(
        self,
        *,
        endpoint_url: str | None = None,
        key: str | None = None,
        secret: str | None = None,
    ) -> None:
        access = key or os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("MINIO_ROOT_USER")
        secret_key = secret or os.environ.get("AWS_SECRET_ACCESS_KEY") or os.environ.get("MINIO_ROOT_PASSWORD")
        endpoint = endpoint_url or os.environ.get("MINIO_ENDPOINT") or os.environ.get("AWS_S3_ENDPOINT", "minio:9000")
        endpoint = str(endpoint).replace("http://", "").replace("https://", "")
        if ":" not in endpoint and endpoint:
            endpoint = f"{endpoint}:9000" if endpoint == "minio" else endpoint
        self._endpoint = f"http://{endpoint}"
        self._access = access or ""
        self._secret = secret_key or ""
        self._fs: object | None = None

    def _get_fs(self):
        if self._fs is None:
            try:
                import s3fs
            except ImportError as e:
                raise ImportError(
                    "S3Backend requires s3fs. Install with: pip install s3fs fsspec"
                ) from e
            self._fs = s3fs.S3FileSystem(
                key=self._access,
                secret=self._secret,
                client_kwargs={"endpoint_url": self._endpoint, "region_name": "us-east-1"},
                config_kwargs={"signature_version": "s3v4", "s3": {"addressing_style": "path"}},
                use_ssl=False,
            )
        return self._fs

    def _norm_uri(self, uri: Union[str, Path]) -> str:
        """Convert s3a:// to s3:// for s3fs compatibility."""
        s = str(uri)
        if s.startswith("s3a://"):
            return "s3://" + s[6:]
        return s

    def list_csv_paths(self, location: Union[str, Path]) -> list[str]:
        fs = self._get_fs()
        path = self._norm_uri(location)
        if not path.endswith("/"):
            path = path + "/"
        try:
            all_paths = fs.find(path, withdirs=False)
            csv_paths = sorted(p for p in all_paths if p.endswith(".csv"))
            return csv_paths
        except Exception as e:
            raise RuntimeError(f"Failed to list CSV paths in {path}") from e

    def read_text(
        self,
        uri: Union[str, Path],
        *,
        encoding: str = "utf-8",
        fallback_encoding: Union[str, None] = "iso-8859-1",
    ) -> str:
        fs = self._get_fs()
        path = self._norm_uri(uri)
        try:
            with fs.open(path, "r", encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            if fallback_encoding is None:
                raise
            with fs.open(path, "r", encoding=fallback_encoding) as f:
                return f.read()

    def read_parquet(self, uri: Union[str, Path]) -> Any:
        import pandas as pd

        fs = self._get_fs()
        path = self._norm_uri(uri)
        with fs.open(path, "rb") as f:
            return pd.read_parquet(f)

    def write_parquet(self, df: Any, uri: Union[str, Path]) -> None:
        fs = self._get_fs()
        path = self._norm_uri(uri)
        self.ensure_output_parent(uri)
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        buf.seek(0)
        with fs.open(path, "wb") as f:
            f.write(buf.read())

    def write_text(self, uri: Union[str, Path], content: str) -> None:
        fs = self._get_fs()
        path = self._norm_uri(uri)
        with fs.open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def exists(self, uri: Union[str, Path]) -> bool:
        fs = self._get_fs()
        path = self._norm_uri(uri)
        return fs.exists(path)

    def ensure_output_parent(self, uri: Union[str, Path]) -> None:
        pass

    def stem(self, uri: Union[str, Path]) -> str:
        return Path(uri).stem

    def name(self, uri: Union[str, Path]) -> str:
        return Path(uri).name


def get_backend(location: Union[str, Path]) -> StorageBackend:
    """
    Return the appropriate storage backend for the given location.

    For s3:// or s3a:// returns S3Backend (requires s3fs).
    For local paths returns FilesystemBackend.
    """
    uri = str(location)
    if uri.startswith(("s3://", "s3a://")):
        return S3Backend()
    return FilesystemBackend()
