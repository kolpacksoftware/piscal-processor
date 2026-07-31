"""Tests for parse_curve_file_json and the piscal-processor-parse-file CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from piscal_processor import cli
from piscal_processor.converter import parse_curve_file_json
from piscal_processor.schema import STANDARD_MEASUREMENT_COLUMNS, STANDARD_METADATA_COLUMNS
from piscal_processor.storage import FilesystemBackend


FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> Path:
    return FIXTURES / name


def test_parse_curve_file_json_sampleinput():
    path = _fixture("sampleinput.csv")
    if not path.exists():
        pytest.skip("fixture sampleinput.csv not found")

    result = parse_curve_file_json(
        str(path), FilesystemBackend(), source_pathway="C3_photosynthesis_leafweb"
    )

    assert set(result.keys()) == {"metadata", "measurements"}
    meta = result["metadata"]
    assert list(meta.keys()) == STANDARD_METADATA_COLUMNS
    assert meta["curve_id"] == "sampleinput"
    assert meta["source_file"] == "sampleinput.csv"
    assert meta["pathway_subtype"] == "C3_photosynthesis_leafweb"
    # Legacy Latitude(Degrees) alias resolves to Latitude
    assert meta["Latitude"] is not None
    assert "Latitude(Degrees)" not in meta

    measurements = result["measurements"]
    assert len(measurements) >= 10
    assert list(measurements[0].keys()) == STANDARD_MEASUREMENT_COLUMNS
    # Measurement aliases (!Ci / !CO2i, !StomCond, etc.) resolve
    assert measurements[0]["pathway_subtype"] == "C3_photosynthesis_leafweb"
    assert measurements[0]["StomCond"] is not None or measurements[0]["PARi"] is not None
    # JSON-safe: no NaN floats
    payload = json.dumps(result, allow_nan=False)
    assert "NaN" not in payload


def test_parse_curve_file_json_leafweb_updated_aliases():
    path = _fixture("sample_leafweb_updated.csv")
    if not path.exists():
        pytest.skip("fixture sample_leafweb_updated.csv not found")

    result = parse_curve_file_json(str(path), FilesystemBackend())
    meta = result["metadata"]
    # LfPhosphContent -> LfPhosphorusContent (key present under canonical name only)
    assert "LfPhosphorusContent" in meta
    assert "LfPhosphContent" not in meta

    row = result["measurements"][0]
    assert row["AnetCO2"] is not None
    assert row["CO2i"] is not None
    assert row["AirPress"] is not None
    assert row["OxygenLevel"] is not None
    assert row["ObsNo"] is not None


def test_parse_curve_file_json_sample_curve():
    path = _fixture("sample_curve.csv")
    if not path.exists():
        pytest.skip("fixture sample_curve.csv not found")

    result = parse_curve_file_json(str(path), FilesystemBackend(), source_pathway="C4")
    assert result["metadata"]["curve_id"] == "sample_curve"
    assert result["metadata"]["pathway_subtype"] == "C4"
    assert len(result["measurements"]) >= 1


def test_parse_file_main_ok(monkeypatch, capsys):
    path = _fixture("sampleinput.csv")
    if not path.exists():
        pytest.skip("fixture sampleinput.csv not found")

    monkeypatch.setattr(
        cli,
        "_parse_parse_file_args",
        lambda: type(
            "Args",
            (),
            {
                "file": str(path),
                "source_pathway": "C3_photosynthesis_leafweb",
                "output": None,
            },
        )(),
    )

    cli.parse_file_main()

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["metadata"]["curve_id"] == "sampleinput"
    assert data["metadata"]["pathway_subtype"] == "C3_photosynthesis_leafweb"
    assert len(data["measurements"]) >= 1
    assert captured.err == ""


def test_parse_file_main_failure(monkeypatch, capsys, tmp_path: Path):
    bad = tmp_path / "not_piscal.csv"
    bad.write_text("a,b\n1,2\n", encoding="utf-8")

    monkeypatch.setattr(
        cli,
        "_parse_parse_file_args",
        lambda: type(
            "Args",
            (),
            {"file": str(bad), "source_pathway": None, "output": None},
        )(),
    )

    with pytest.raises(SystemExit) as excinfo:
        cli.parse_file_main()

    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "error:" in err
