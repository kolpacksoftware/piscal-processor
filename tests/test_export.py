"""Tests for piscal_processor.export."""

import io
from pathlib import Path

import pandas as pd
import pytest

from piscal_processor.export import export_curves, extract_columns


def test_extract_columns_none_uses_standard_order():
    df = pd.DataFrame({"curve_id": [1, 2], "AnetCO2": [10, 20], "PARi": [100, 200]})
    out = extract_columns(df, columns=None)
    assert list(out.columns) == ["curve_id", "AnetCO2", "PARi"]  # standard order for existing


def test_extract_columns_subset():
    df = pd.DataFrame({"curve_id": [1], "AnetCO2": [10], "PARi": [100]})
    out = extract_columns(df, columns=["curve_id", "AnetCO2"])
    assert list(out.columns) == ["curve_id", "AnetCO2"]


def test_export_curves_to_buffer_csv():
    df = pd.DataFrame({"curve_id": ["c1"], "AnetCO2": [25.0]})
    buf = io.StringIO()
    export_curves(df, buf, columns=["curve_id", "AnetCO2"], format="csv")
    content = buf.getvalue()
    assert "curve_id" in content
    assert "AnetCO2" in content
    assert "c1" in content
    assert "," in content


def test_export_curves_to_buffer_tsv():
    df = pd.DataFrame({"curve_id": ["c1"], "AnetCO2": [25.0]})
    buf = io.StringIO()
    export_curves(df, buf, columns=["curve_id", "AnetCO2"], format="tsv")
    content = buf.getvalue()
    assert "curve_id" in content
    assert "\t" in content


def test_export_curves_to_path(tmp_path):
    df = pd.DataFrame({"curve_id": ["c1"], "AnetCO2": [25.0]})
    out_path = tmp_path / "out.csv"
    export_curves(df, out_path, columns=["curve_id", "AnetCO2"], format="csv")
    assert out_path.exists()
    assert "curve_id" in out_path.read_text()
