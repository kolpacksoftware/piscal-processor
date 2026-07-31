"""Tests for parse_curve_file_json and the piscal-processor-parse-file CLI."""

from __future__ import annotations

import json
import logging
import sys
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
    # Legacy Latitude(Degrees) / Longitude(Degrees) aliases carry their values across
    assert meta["Latitude"] == 38.733
    assert meta["Longitude"] == -92.2

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
    # Assert on values, not key presence: every STANDARD_METADATA_COLUMNS key is
    # present by construction, so key checks cannot detect a broken alias.
    assert meta["Latitude"] == 35.0
    assert meta["Longitude"] == -82.0
    assert meta["LfPhosphorusContent"] == 0.2
    assert meta["param_Gamma"] == 42.0

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


def test_legacy_metadata_headers_resolve_to_canonical_keys(tmp_path: Path):
    """Cover the METADATA_COLUMN_ALIASES entries no fixture exercises with real values."""
    source = _fixture("sample_leafweb_updated.csv")
    if not source.exists():
        pytest.skip("fixture sample_leafweb_updated.csv not found")

    lines = source.read_text(encoding="utf-8").splitlines()
    site_idx = next(i for i, line in enumerate(lines) if line.startswith("SiteID"))
    # The fixture already uses the canonical spelling; swap in the legacy one.
    lines[site_idx] = lines[site_idx].replace("LfPhosphorusContent", "LfPhosphContent")
    # The legacy parameter block is all -9999 sentinels, so give each column a
    # distinct value to prove it lands under the right canonical key.
    param_idx = next(i for i, line in enumerate(lines) if line.startswith("Gamma*25"))
    lines[param_idx + 2] = "41,42,43,44,45,46,47"

    legacy = tmp_path / "legacy_headers.csv"
    legacy.write_text("\n".join(lines) + "\n", encoding="utf-8")

    meta = parse_curve_file_json(str(legacy), FilesystemBackend())["metadata"]

    assert meta["LfPhosphorusContent"] == 0.2
    assert meta["param_Gamma"] == 41.0
    assert meta["param_Kc25"] == 42.0
    assert meta["param_Ko25"] == 43.0
    assert meta["param_AlphaTPU"] == 44.0
    assert meta["param_Rd25"] == 45.0
    assert meta["param_ResistWP25"] == 46.0
    assert meta["param_ResistCH25"] == 47.0


def test_parse_file_main_ok(monkeypatch, capsys, caplog):
    path = _fixture("sampleinput.csv")
    if not path.exists():
        pytest.skip("fixture sampleinput.csv not found")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "piscal-processor-parse-file",
            str(path),
            "--source-pathway",
            "C3_photosynthesis_leafweb",
        ],
    )

    with caplog.at_level(logging.WARNING):
        cli.parse_file_main()

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["metadata"]["curve_id"] == "sampleinput"
    assert data["metadata"]["pathway_subtype"] == "C3_photosynthesis_leafweb"
    assert len(data["measurements"]) >= 1

    # stdout must stay pipeable: exactly one JSON document, no diagnostics mixed in.
    assert captured.out.count("\n") == 1
    warning = "required measurement columns"
    assert any(warning in record.getMessage() for record in caplog.records)
    assert warning not in captured.out


def test_parse_file_main_writes_output_file(monkeypatch, capsys, tmp_path: Path):
    path = _fixture("sampleinput.csv")
    if not path.exists():
        pytest.skip("fixture sampleinput.csv not found")
    out_path = tmp_path / "curve.json"

    monkeypatch.setattr(
        sys,
        "argv",
        ["piscal-processor-parse-file", str(path), "-o", str(out_path)],
    )

    cli.parse_file_main()

    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["metadata"]["curve_id"] == "sampleinput"
    # --source-pathway is optional and defaults to no label
    assert data["metadata"]["pathway_subtype"] is None
    assert len(data["measurements"]) >= 1
    assert capsys.readouterr().out == ""


def test_parse_file_main_non_finite_values_are_null(monkeypatch, capsys, tmp_path: Path):
    path = _fixture("sampleinput.csv")
    if not path.exists():
        pytest.skip("fixture sampleinput.csv not found")

    lines = path.read_text(encoding="utf-8").splitlines()
    header_idx = next(i for i, line in enumerate(lines) if line.startswith("Obs,"))
    column_idx = lines[header_idx].split(",").index("!StomCond")
    first_row = lines[header_idx + 2].split(",")
    first_row[column_idx] = "inf"
    lines[header_idx + 2] = ",".join(first_row)

    infinite = tmp_path / "infinite.csv"
    infinite.write_text("\n".join(lines) + "\n", encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["piscal-processor-parse-file", str(infinite)])

    cli.parse_file_main()

    data = json.loads(capsys.readouterr().out)
    assert data["measurements"][0]["StomCond"] is None


def test_parse_file_main_serialization_failure_writes_nothing(
    monkeypatch, capsys, tmp_path: Path
):
    path = _fixture("sampleinput.csv")
    if not path.exists():
        pytest.skip("fixture sampleinput.csv not found")
    out_path = tmp_path / "curve.json"

    # A value json cannot encode, to prove nothing is written until encoding succeeds.
    monkeypatch.setattr(
        cli,
        "parse_curve_file_json",
        lambda *args, **kwargs: {"metadata": {"curve_id": {"unencodable"}}, "measurements": []},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["piscal-processor-parse-file", str(path), "-o", str(out_path)],
    )

    with pytest.raises(SystemExit) as excinfo:
        cli.parse_file_main()

    assert excinfo.value.code == 1
    assert not out_path.exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err


def test_parse_file_main_failure(monkeypatch, capsys, tmp_path: Path):
    bad = tmp_path / "not_piscal.csv"
    bad.write_text("a,b\n1,2\n", encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["piscal-processor-parse-file", str(bad)])

    with pytest.raises(SystemExit) as excinfo:
        cli.parse_file_main()

    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "error:" in captured.err
    # A failure must not leave a partial document on stdout.
    assert captured.out == ""
