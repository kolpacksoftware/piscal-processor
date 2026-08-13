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


def test_measurement_aliases_include_chamber_area():
    assert MEASUREMENT_COLUMN_ALIASES["ChamberArea"] == "LeafAreaMeasured"
    assert MEASUREMENT_COLUMN_ALIASES["Area"] == "LeafAreaMeasured"


def test_gfs_cornell_param_aliases_map_to_standard():
    expected = {
        "param_Gamma*_25oC": "param_Gamma",
        "param_Kc_25oC": "param_Kc25",
        "param_Ko_25oC": "param_Ko25",
        "param_Alpha_25oC": "param_AlphaTPU",
        "param_Rd_25oC": "param_Rd25",
        "param_rwp_25oC": "param_ResistWP25",
        "param_rch_25oC": "param_ResistCH25",
    }
    for alias, standard in expected.items():
        assert METADATA_COLUMN_ALIASES[alias] == standard
