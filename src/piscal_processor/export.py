"""Export measurement/curve data to CSV or TSV."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Union

import pandas as pd

from piscal_processor.schema import STANDARD_MEASUREMENT_COLUMNS
from piscal_processor.storage import get_backend


def extract_columns(
    measurements_df: pd.DataFrame,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """
    Select columns from a measurements DataFrame.

    If columns is None, returns the DataFrame reindexed to STANDARD_MEASUREMENT_COLUMNS
    (only columns that exist). Otherwise returns only the requested columns that exist.
    """
    if columns is None:
        # Use standard order; only include columns that exist
        available = [c for c in STANDARD_MEASUREMENT_COLUMNS if c in measurements_df.columns]
        return measurements_df.reindex(columns=available)
    available = [c for c in columns if c in measurements_df.columns]
    return measurements_df[available]


def export_curves(
    measurements_df: pd.DataFrame,
    path_or_buffer: Union[str, Path, io.StringIO],
    *,
    columns: list[str] | None = None,
    format: str = "csv",
    metadata_df: pd.DataFrame | None = None,
    include_metadata: bool = False,
) -> None:
    """
    Export measurement rows to CSV or TSV.

    Args:
        measurements_df: DataFrame of curve measurements (e.g. from convert_curves).
        path_or_buffer: Output path (str/Path) or file-like (e.g. io.StringIO).
        columns: If None, export all columns in standard order; else export only these.
        format: "csv" or "tsv" (delimiter).
        metadata_df: Optional metadata DataFrame (one row per curve).
        include_metadata: If True and metadata_df is provided, join on curve_id then export.
    """
    sep = "\t" if format.lower() == "tsv" else ","
    df = extract_columns(measurements_df, columns=columns)
    if include_metadata and metadata_df is not None:
        df = df.merge(metadata_df, on="curve_id", how="left", suffixes=("", "_meta"))
        # Drop duplicate columns from merge (e.g. curve_id_meta if any)
        to_drop = [c for c in df.columns if c.endswith("_meta")]
        if to_drop:
            df = df.drop(columns=to_drop)

    if isinstance(path_or_buffer, (str, Path)):
        buf = io.StringIO()
        df.to_csv(buf, sep=sep, index=False)
        content = buf.getvalue()
        backend = get_backend(str(path_or_buffer))
        backend.ensure_output_parent(str(path_or_buffer))
        backend.write_text(path_or_buffer, content)
    else:
        df.to_csv(path_or_buffer, sep=sep, index=False)
