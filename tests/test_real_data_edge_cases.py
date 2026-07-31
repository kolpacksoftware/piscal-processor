"""Edge cases taken from the real Leafweb corpus (StandardDataForAI).

Each fixture here is an unmodified file from the archive, kept because it exercises
something the synthetic fixtures do not:

  real_quoted_headers.csv   descriptive header lines wrapped in CSV quotes because
                            the value contains commas
  real_nul_padded.csv       fixed-width fields padded with NUL bytes instead of spaces
  real_text_in_numeric.csv  free text ("HIGH") in a column the schema declares numeric,
                            plus values written with a leading period (".301")
  real_unnamed_columns.csv  trailing commas in the measurement header, which produce
                            several unnamed columns
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import pandas as pd
import pytest

from piscal_processor.converter import (
    convert_curves,
    normalize_and_write_parquet,
    parse_curve_file_json,
)
from piscal_processor.schema import (
    MEASUREMENT_STRING_COLUMNS,
    NUMERIC_MEASUREMENT_COLUMNS,
    NUMERIC_METADATA_COLUMNS,
    STRING_METADATA_COLUMNS,
)
from piscal_processor.storage import FilesystemBackend


FIXTURES = Path(__file__).parent / "fixtures"
ALL_FIXTURES = sorted(p.name for p in FIXTURES.glob("*.csv"))


def _parse(name: str) -> dict:
    path = FIXTURES / name
    if not path.exists():
        pytest.skip(f"fixture {name} not found")
    return parse_curve_file_json(str(path), FilesystemBackend())


def test_csv_quoted_header_lines_keep_key_and_value_intact():
    meta = _parse("real_quoted_headers.csv")["metadata"]

    # The quote that wraps the line must not survive on either side of the colon,
    # and the commas that forced the quoting must still be part of the value.
    assert meta["Site name in full"] == "Central Grasslands REC greenhouse, south-central North Dakota"
    assert meta["Major species"].startswith("Poa pratensis, Oligoneuron rigidum")
    assert meta["Sample leaf light environment"] == "Greenhouse, 900 umol/m2/s"
    assert meta["Contact information"].startswith("Xuejun.Dong@ndsu.edu/")

    for key, value in meta.items():
        assert not key.startswith('"'), key
        if isinstance(value, str):
            assert not value.endswith('"'), f"{key}={value!r}"


def test_nul_padded_fields_are_treated_as_missing():
    result = _parse("real_nul_padded.csv")
    meta = result["metadata"]

    # These fields hold only NUL padding in the source file.
    assert meta["SampleYear"] is None
    assert meta["SampleDayOfYear"] is None
    # Real values in the same file still come through.
    assert meta["Latitude"] == 9.074
    assert meta["SiteID"] == "PA-Gam_NA"

    # No NUL byte may reach the payload.
    assert "\x00" not in json.dumps(result)
    assert "\\u0000" not in json.dumps(result)


def test_free_text_in_a_numeric_column_is_dropped_and_reported(caplog):
    path = FIXTURES / "real_text_in_numeric.csv"
    if not path.exists():
        pytest.skip("fixture real_text_in_numeric.csv not found")

    with caplog.at_level(logging.WARNING):
        meta = parse_curve_file_json(str(path), FilesystemBackend())["metadata"]

    # Sapwooddensity is genuinely numeric (g/cm3); this file writes "HIGH" instead.
    assert meta["Sapwooddensity"] is None
    assert any("Sapwooddensity='HIGH'" in r.getMessage() for r in caplog.records)

    # Values written with a leading period still parse.
    assert meta["LfNitrogenContent"] == 0.301


def test_unnamed_trailing_columns_do_not_break_reindexing():
    """Repeated empty header names used to raise "cannot reindex on an axis with
    duplicate labels" and take out both the JSON and the Parquet path."""
    result = _parse("real_unnamed_columns.csv")

    assert len(result["measurements"]) == 11
    first = result["measurements"][0]
    assert first["Year"] == 2022.0
    assert first["AnetCO2"] == -1.02


def test_categorical_wood_porosity_is_not_coerced_to_a_number():
    """WoodPorosity is categorical, so it must not sit in NUMERIC_METADATA_COLUMNS."""
    assert "WoodPorosity" not in NUMERIC_METADATA_COLUMNS
    meta = _parse("sample_leafweb_updated.csv")["metadata"]
    assert meta["WoodPorosity"] == "ring porous"


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_every_column_matches_its_declared_type(name: str):
    """A field's JSON type comes from the schema, never from the file's contents."""
    result = _parse(name)

    meta = result["metadata"]
    for col in NUMERIC_METADATA_COLUMNS:
        assert meta[col] is None or isinstance(meta[col], float), f"{col} in {name}"
    for col in STRING_METADATA_COLUMNS:
        assert meta[col] is None or isinstance(meta[col], str), f"{col} in {name}"

    for row in result["measurements"]:
        for col in NUMERIC_MEASUREMENT_COLUMNS:
            assert row[col] is None or isinstance(row[col], float), f"{col} in {name}"
        for col in MEASUREMENT_STRING_COLUMNS:
            assert row[col] is None or isinstance(row[col], str), f"{col} in {name}"


@pytest.mark.parametrize(
    "names",
    [[name] for name in ALL_FIXTURES] + [ALL_FIXTURES],
    ids=ALL_FIXTURES + ["all-together"],
)
def test_parquet_dtypes_do_not_depend_on_the_batch(tmp_path: Path, names: list[str]):
    """Parquet must declare the same types the JSON payload uses, per file and in bulk.

    Converting files together hides per-file dtype drift, because a column that is
    int64 in one file and float64 in another lands on float64 after the concat. Each
    fixture is therefore also converted on its own.
    """
    source = tmp_path / "in"
    source.mkdir()
    for name in names:
        shutil.copy(FIXTURES / name, source)

    backend = FilesystemBackend()
    metadata_df, measurement_df = convert_curves(str(source), backend, source_pathway="C3")
    output = tmp_path / "pq"
    output.mkdir()
    normalize_and_write_parquet(metadata_df, measurement_df, output)

    written_metadata = pd.read_parquet(output / "curve_metadata.parquet")
    written_measurements = pd.read_parquet(output / "curve_measurements.parquet")

    for col in NUMERIC_METADATA_COLUMNS:
        assert written_metadata[col].dtype == "float64", col
    for col in STRING_METADATA_COLUMNS:
        assert written_metadata[col].dtype == "string", col
    for col in NUMERIC_MEASUREMENT_COLUMNS:
        assert written_measurements[col].dtype == "float64", col
    for col in MEASUREMENT_STRING_COLUMNS:
        assert written_measurements[col].dtype == "string", col


def test_parquet_keeps_categorical_wood_porosity(tmp_path: Path):
    source = tmp_path / "in"
    source.mkdir()
    shutil.copy(FIXTURES / "sample_leafweb_updated.csv", source)

    metadata_df, measurement_df = convert_curves(str(source), FilesystemBackend())
    output = tmp_path / "pq"
    output.mkdir()
    normalize_and_write_parquet(metadata_df, measurement_df, output)

    written = pd.read_parquet(output / "curve_metadata.parquet")
    assert written["WoodPorosity"].iloc[0] == "ring porous"
