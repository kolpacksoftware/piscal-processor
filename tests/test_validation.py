"""Tests for piscal_processor.validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from piscal_processor.validation import is_piscal_csv, validate_piscal_csv


FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> Path:
    return FIXTURES / name


def test_is_piscal_csv_accepts_sampleinput():
    assert is_piscal_csv(_fixture("sampleinput.csv"))


def test_is_piscal_csv_accepts_sample_curve():
    assert is_piscal_csv(_fixture("sample_curve.csv"))


def test_is_piscal_csv_accepts_leafweb_updated():
    assert is_piscal_csv(_fixture("sample_leafweb_updated.csv"))


def test_validate_piscal_csv_rejects_non_piscal_file(tmp_path: Path):
    # Simple non-PISCAL CSV (no header key/value section, no triplets)
    bad = tmp_path / "not_piscal.csv"
    bad.write_text("a,b\n1,2\n", encoding="utf-8")

    ok, errors = validate_piscal_csv(bad)
    assert not ok
    assert errors


def test_validate_piscal_csv_rejects_missing_param_block(tmp_path: Path):
    # Construct a file with header + site triplet but no parameter triplet.
    content = "\n".join(
        [
            "Photosynthetic pathway: C3",
            "Investigator name: Test",
            "Site name in full: Test Site",
            "SiteID,SpeciesSampled,SampleYear",
            "NA,NA,NA",
            "site1,SpeciesA,2024",
            # Intentionally jump straight to measurement header without parameters
            "DataType,ObsNo,Year,DayOfYear,ObsDate,HHMMSS,!AnetCO2,!PARi,!Tleaf",
            "NA,NA,NA,NA,NA,NA,µmol,µmol,°C",
            "ACi,1,2024,100,2024-04-10,10:00:00,25.5,1200,28.0",
        ]
    )
    path = tmp_path / "missing_param.csv"
    path.write_text(content, encoding="utf-8")

    ok, errors = validate_piscal_csv(path)
    assert not ok
    # Should fail specifically due to parameter triplet missing/malformed
    assert any("parameter triplet" in e.lower() or "parameter" in e.lower() for e in errors)


def test_validate_accepts_gfs_cornell_param_headers():
    assert is_piscal_csv(_fixture("real_gfs_cornell.csv"))


def test_validate_accepts_latin1_file():
    path = _fixture("real_latin1.csv")
    ok, errors = validate_piscal_csv(path)
    assert ok, errors


def test_validate_rejects_shifted_triplet():
    ok, errors = validate_piscal_csv(_fixture("real_shifted_triplet.csv"))
    assert not ok
    assert errors

