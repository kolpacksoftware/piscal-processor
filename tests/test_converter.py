"""Tests for piscal_processor.converter."""

from pathlib import Path

import pandas as pd
import pytest

from piscal_processor.converter import convert_curves, parse_curve_file
from piscal_processor.storage import FilesystemBackend


def test_parse_curve_file_fixture():
    fixtures = Path(__file__).parent / "fixtures"
    csv_path = fixtures / "sample_curve.csv"
    if not csv_path.exists():
        pytest.skip("fixture not found")
    backend = FilesystemBackend()
    meta, meas = parse_curve_file(str(csv_path), backend)
    assert "curve_id" in meta
    assert meta["curve_id"] == "sample_curve"
    assert "source_file" in meta
    assert "Photosynthetic pathway" in meta
    assert isinstance(meas, pd.DataFrame)
    assert "curve_id" in meas.columns
    assert len(meas) >= 1


def test_parse_curve_file_sampleinput_leafweb():
    """Parse leafweb.org-style sample input (different header names, site/param triplets)."""
    fixtures = Path(__file__).parent / "fixtures"
    csv_path = fixtures / "sampleinput.csv"
    if not csv_path.exists():
        pytest.skip("fixture sampleinput.csv not found")
    backend = FilesystemBackend()
    meta, meas = parse_curve_file(str(csv_path), backend)
    assert meta["curve_id"] == "sampleinput"
    assert meta["source_file"] == "sampleinput.csv"
    assert "Investigator name" in meta
    assert "SiteID" in meta or any("Site" in k for k in meta)
    assert isinstance(meas, pd.DataFrame)
    assert "curve_id" in meas.columns
    # leafweb file has 12 measurement rows (lines 19-30)
    assert len(meas) >= 10
    # Aliases map !StomCond, !PARi, !Tleaf etc. to standard names
    assert "StomCond" in meas.columns or "PARi" in meas.columns


def test_convert_curves_fixture():
    fixtures = Path(__file__).parent / "fixtures"
    if not (fixtures / "sample_curve.csv").exists():
        pytest.skip("fixture not found")
    backend = FilesystemBackend()
    meta_df, meas_df = convert_curves(str(fixtures), backend, source_pathway="C3_test")
    assert len(meta_df) >= 1
    assert len(meas_df) >= 1
    assert "pathway_subtype" in meta_df.columns
    assert meta_df["pathway_subtype"].iloc[0] == "C3_test"
    assert "curve_id" in meas_df.columns


def test_convert_curves_empty_dir(tmp_path):
    backend = FilesystemBackend()
    with pytest.raises(FileNotFoundError, match="No CSV files found"):
        convert_curves(str(tmp_path), backend)
