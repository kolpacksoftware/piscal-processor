"""Tests for piscal_processor.schema."""

import pytest

from piscal_processor.schema import (
    MEASUREMENT_COLUMN_ALIASES,
    METADATA_COLUMN_ALIASES,
    STANDARD_MEASUREMENT_COLUMNS,
    STANDARD_METADATA_COLUMNS,
)


def test_standard_metadata_columns_non_empty():
    assert len(STANDARD_METADATA_COLUMNS) > 0
    assert "curve_id" in STANDARD_METADATA_COLUMNS
    assert "source_file" in STANDARD_METADATA_COLUMNS


def test_standard_measurement_columns_non_empty():
    assert len(STANDARD_MEASUREMENT_COLUMNS) > 0
    assert "curve_id" in STANDARD_MEASUREMENT_COLUMNS
    assert "AnetCO2" in STANDARD_MEASUREMENT_COLUMNS


def test_metadata_aliases_map_to_standard():
    for alias, standard in METADATA_COLUMN_ALIASES.items():
        assert standard in STANDARD_METADATA_COLUMNS, f"{alias} -> {standard}"


def test_measurement_aliases_map_to_standard():
    for alias, standard in MEASUREMENT_COLUMN_ALIASES.items():
        assert standard in STANDARD_MEASUREMENT_COLUMNS, f"{alias} -> {standard}"
