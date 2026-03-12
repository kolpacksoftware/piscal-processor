"""Convert PISCAL CSV curves into metadata and measurement DataFrames and Parquet."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pandas as pd

from piscal_processor.parser import (
    next_nonempty,
    normalize_scalar,
    parse_csv_line,
    parse_key_value_section,
    parse_triplet,
)
from piscal_processor.schema import (
    MEASUREMENT_COLUMN_ALIASES,
    MEASUREMENT_STRING_COLUMNS,
    METADATA_COLUMN_ALIASES,
    NUMERIC_METADATA_COLUMNS,
    STANDARD_MEASUREMENT_COLUMNS,
    STANDARD_METADATA_COLUMNS,
)
from piscal_processor.storage import StorageBackend, get_backend


LOG = logging.getLogger(__name__)

OPTIONAL_MEASUREMENT_COLUMNS = ["BLCond"]


REQUIRED_MEASUREMENT_COLUMNS = [
    # Gas exchange required variables (Leafweb \"!\" inputs)
    "AnetCO2",
    "StomCond",
    "CO2i",
    "Trmmol",
    "VpdL",
    "Tleaf",
    "PARi",
    "AirPress",
]


def _validate_required_measurement_columns(measurements_df: pd.DataFrame) -> None:
    """
    Emit warnings when required Leafweb measurement variables are missing or empty.

    This helper is intentionally non-fatal: it logs a warning but does not raise,
    so callers still receive DataFrames/Parquet outputs even when required inputs
    for Leafweb analyses are incomplete.
    """
    if measurements_df is None or measurements_df.empty:
        return

    missing_or_empty: List[str] = []
    for col in REQUIRED_MEASUREMENT_COLUMNS:
        if col not in measurements_df.columns:
            missing_or_empty.append(col)
            continue
        series = measurements_df[col]
        if series.isna().all():
            missing_or_empty.append(col)

    if missing_or_empty:
        LOG.warning(
            "Leafweb required measurement columns are missing or empty for one or more curves: %s",
            ", ".join(sorted(missing_or_empty)),
        )


def _pathway_subdirs_from_csv_paths(input_dir: str, csv_paths: List[str]) -> List[str]:
    """Return sorted list of immediate subdir names under input_dir that contain CSVs."""
    base = input_dir.rstrip("/")
    if not base:
        return []
    subdirs: Set[str] = set()
    for p in csv_paths:
        p_str = str(p)
        if p_str.startswith(base):
            rest = p_str[len(base) :].lstrip("/")
            if rest:
                subdirs.add(rest.split("/")[0])
    return sorted(subdirs)


def pad_row(row: List[str], target_len: int) -> List[str]:
    """Normalize a CSV row to a fixed length by padding or truncating."""
    if len(row) < target_len:
        return row + ["" for _ in range(target_len - len(row))]
    if len(row) > target_len:
        return row[:target_len]
    return row


def coerce_numeric_columns(df: pd.DataFrame, skip: set[str] | None = None) -> pd.DataFrame:
    """Convert string columns to numeric when they contain numeric data."""
    skip = skip or set()
    for column in df.columns:
        if column in skip:
            continue
        numeric = pd.to_numeric(df[column], errors="coerce")
        if numeric.notna().any():
            df[column] = numeric
    return df


def parse_curve_file(uri: str, backend: StorageBackend) -> Tuple[Dict[str, object], pd.DataFrame]:
    """Parse a single PISCAL CSV file into metadata dict and measurements DataFrame."""
    lines = backend.read_text(uri).splitlines()

    idx, general_info = parse_key_value_section(lines)
    idx, site_headers, _site_units, site_values = parse_triplet(lines, idx)
    site_data = {
        header.strip(): normalize_scalar(value)
        for header, value in zip(site_headers, site_values)
    }

    idx, param_headers, param_units, param_values = parse_triplet(lines, idx)
    param_data = {
        f"param_{header.strip()}": normalize_scalar(value)
        for header, value in zip(param_headers, param_values)
    }

    idx = next_nonempty(lines, idx)
    measurement_headers = parse_csv_line(lines[idx])
    idx += 1
    idx = next_nonempty(lines, idx)
    measurement_units = parse_csv_line(lines[idx])
    idx += 1

    data_rows: List[List[str]] = []
    while idx < len(lines):
        line = lines[idx]
        idx += 1
        if not line.strip():
            continue
        row = parse_csv_line(line)
        if not row:
            continue
        data_rows.append(pad_row(row, len(measurement_headers)))

    measurements_df = pd.DataFrame(data_rows, columns=measurement_headers)
    measurements_df = measurements_df.rename(
        columns={k: v for k, v in MEASUREMENT_COLUMN_ALIASES.items() if k in measurements_df.columns}
    )
    measurements_df.insert(0, "curve_id", backend.stem(uri))

    insert_idx = 1
    if "SpeciesSampled" in site_data:
        measurements_df.insert(insert_idx, "SpeciesSampled", site_data.get("SpeciesSampled"))
        insert_idx += 1
    if "Major species" in general_info:
        measurements_df.insert(insert_idx, "Major_species", general_info.get("Major species"))
        insert_idx += 1
    if "Photosynthetic pathway" in general_info:
        measurements_df.insert(insert_idx, "Photosynthetic_pathway", general_info.get("Photosynthetic pathway"))
        insert_idx += 1

    measurements_df.replace(r"^-9999(\.0+)?$", pd.NA, regex=True, inplace=True)
    measurements_df.replace("NA", pd.NA, inplace=True)

    coerce_numeric_columns(
        measurements_df,
        skip={"HHMMSS", "curve_id", "SpeciesSampled", "Major_species", "Photosynthetic_pathway", "DataType", "ObsDate"},
    )

    for col in OPTIONAL_MEASUREMENT_COLUMNS:
        if col not in measurements_df.columns:
            measurements_df[col] = pd.NA

    _validate_required_measurement_columns(measurements_df)

    metadata_row: Dict[str, object] = {
        "curve_id": backend.stem(uri),
        "source_file": backend.name(uri),
        **general_info,
        **site_data,
        **param_data,
        "measurement_units": json.dumps(
            {key.strip(): unit.strip() for key, unit in zip(measurement_headers, measurement_units)}
        ),
        "parameter_units": json.dumps(
            {key.replace("param_", ""): unit.strip() for key, unit in zip(param_headers, param_units)}
        ),
    }

    return metadata_row, measurements_df


def convert_curves(
    input_dir: str | Path,
    backend: StorageBackend,
    *,
    source_pathway: str | None = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Convert all CSV files in a directory into combined metadata and measurement DataFrames."""
    curve_files = backend.list_csv_paths(input_dir)
    if not curve_files:
        raise FileNotFoundError(f"No CSV files found in {input_dir}")

    metadata_rows: List[Dict[str, object]] = []
    measurement_frames: List[pd.DataFrame] = []

    for uri in curve_files:
        metadata_row, measurement_df = parse_curve_file(uri, backend)
        metadata_rows.append(metadata_row)
        measurement_frames.append(measurement_df)

    all_columns = STANDARD_MEASUREMENT_COLUMNS

    def _align_frame(df: pd.DataFrame) -> pd.DataFrame:
        out = df.reindex(columns=all_columns, fill_value=pd.NA)
        for col in OPTIONAL_MEASUREMENT_COLUMNS:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce")
        all_na = out.columns[out.isna().all()].tolist()
        if all_na:
            out = out.drop(columns=all_na)
        return out

    measurement_frames = [_align_frame(df) for df in measurement_frames]

    metadata_df = pd.DataFrame(metadata_rows)
    measurement_df = pd.concat(measurement_frames, ignore_index=True, join="outer")
    measurement_df = measurement_df.reindex(columns=STANDARD_MEASUREMENT_COLUMNS)

    if source_pathway:
        metadata_df.insert(1, "pathway_subtype", source_pathway)
        measurement_df["pathway_subtype"] = source_pathway

    return metadata_df, measurement_df


def normalize_and_write_parquet(
    metadata_df: pd.DataFrame,
    measurement_df: pd.DataFrame,
    output_dir: Path,
    *,
    metadata_name: str = "curve_metadata.parquet",
    measurements_name: str = "curve_measurements.parquet",
) -> None:
    """Normalize schema and write both Parquet tables under output_dir."""
    metadata_path = output_dir / metadata_name
    measurement_path = output_dir / measurements_name
    write_backend = get_backend(str(output_dir))
    write_backend.ensure_output_parent(str(metadata_path))
    write_backend.ensure_output_parent(str(measurement_path))

    metadata_df = metadata_df.rename(
        columns={k: v for k, v in METADATA_COLUMN_ALIASES.items() if k in metadata_df.columns}
    )
    if metadata_df.columns.duplicated().any():
        metadata_df = metadata_df.loc[:, ~metadata_df.columns.duplicated(keep="first")]
    metadata_df = metadata_df.reindex(columns=STANDARD_METADATA_COLUMNS)

    for col in metadata_df.select_dtypes(include=["object", "string"]).columns:
        metadata_df[col] = metadata_df[col].apply(lambda x: pd.NA if pd.isna(x) else str(x))
    for col in NUMERIC_METADATA_COLUMNS:
        if col in metadata_df.columns:
            metadata_df[col] = pd.to_numeric(metadata_df[col], errors="coerce").astype("float64")

    for col in MEASUREMENT_STRING_COLUMNS:
        if col in measurement_df.columns:
            s = measurement_df[col]
            measurement_df[col] = s.apply(lambda x: pd.NA if pd.isna(x) else str(x)).astype("string")

    write_backend.write_parquet(metadata_df, metadata_path)
    write_backend.write_parquet(measurement_df, measurement_path)
