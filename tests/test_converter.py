"""Tests for piscal_processor.converter."""

from pathlib import Path

import pandas as pd
import pytest

from piscal_processor.converter import (
    convert_curves,
    normalize_and_write_parquet,
    parse_curve_file,
)
from piscal_processor.storage import FilesystemBackend, get_backend


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


def test_two_headers_aliasing_to_one_column_keep_the_first(tmp_path):
    """MEASUREMENT_COLUMN_ALIASES maps several spellings onto one standard column.

    A file carrying two of them (here AirPres and Patm, both AirPress) would otherwise
    produce duplicate labels and break the reindex onto the standard schema.
    """
    fixtures = Path(__file__).parent / "fixtures"
    source = fixtures / "sample_leafweb_updated.csv"
    if not source.exists():
        pytest.skip("fixture sample_leafweb_updated.csv not found")

    lines = source.read_text(encoding="utf-8").splitlines()
    header_idx = next(i for i, line in enumerate(lines) if line.startswith("DataType,"))
    headers = lines[header_idx].split(",")
    headers[headers.index("!AirPress")] = "AirPres"
    lines[header_idx] = ",".join(headers) + ",Patm"
    lines[header_idx + 1] += ",kPa"
    for row in range(header_idx + 2, len(lines)):
        if lines[row].strip():
            lines[row] += ",99.9"

    collided = tmp_path / "aliased.csv"
    collided.write_text("\n".join(lines) + "\n", encoding="utf-8")

    _, measurements = parse_curve_file(str(collided), FilesystemBackend())

    assert list(measurements.columns).count("AirPress") == 1
    # The first spelling in the header wins; the fixture's own value is 101.3.
    assert measurements["AirPress"].iloc[0] == 101.3


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
    # Org-site Latitude(Degrees) is canonicalized in parse_curve_file.
    assert meta["Latitude"] == 38.733
    assert "Latitude(Degrees)" not in meta
    # Photo and !AdjPhoto are both real; AnetCO2 stays AdjPhoto, Photo stays its own column.
    assert "Photo" in meas.columns
    assert meas["Photo"].iloc[0] == pytest.approx(7.51)
    assert meas["AnetCO2"].iloc[0] == pytest.approx(7.470041223)


def test_parse_curve_file_leafweb_updated_headers():
    """Parse updated Leafweb-style CSV and ensure aliases normalize correctly."""
    fixtures = Path(__file__).parent / "fixtures"
    csv_path = fixtures / "sample_leafweb_updated.csv"
    if not csv_path.exists():
        pytest.skip("fixture sample_leafweb_updated.csv not found")
    backend = FilesystemBackend()
    meta, meas = parse_curve_file(str(csv_path), backend)

    assert meta["curve_id"] == "sample_leafweb_updated"
    assert meta["source_file"] == "sample_leafweb_updated.csv"
    # Metadata alias: LfPhosphContent -> LfPhosphorusContent (via METADATA_COLUMN_ALIASES)
    assert "LfPhosphorusContent" in meta or "LfPhosphContent" in meta

    assert "curve_id" in meas.columns
    # Measurement aliases: !AnetCO2, !CO2i, OxygenLevel%, VOCS, Flow/Obs, etc.
    assert "AnetCO2" in meas.columns
    assert "CO2i" in meas.columns
    assert "AirPress" in meas.columns
    assert "OxygenLevel" in meas.columns
    assert "VOCS_reading" in meas.columns
    assert "MainFlowRate" in meas.columns
    assert "ObsNo" in meas.columns


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


def test_metadata_samplelighting_samplecondition_remain_strings(tmp_path):
    """Ensure SampleLighting and SampleCondition are not coerced to numeric."""
    backend = FilesystemBackend()
    output_dir = tmp_path / "out"

    metadata_df = pd.DataFrame(
        [
            {
                "curve_id": "curve1",
                "pathway_subtype": "C3",
                "source_file": "curve1.csv",
                "SampleLighting": "Sunlit",
                "SampleCondition": "Well-hydrated",
            }
        ]
    )
    measurement_df = pd.DataFrame(
        [
            {
                "curve_id": "curve1",
                "pathway_subtype": "C3",
            }
        ]
    )

    normalize_and_write_parquet(metadata_df, measurement_df, output_dir)

    meta_path = output_dir / "curve_metadata.parquet"
    read_backend = get_backend(str(output_dir))
    roundtrip_meta = read_backend.read_parquet(meta_path)

    # After parquet round-trip, these should remain string-like columns
    sl = roundtrip_meta["SampleLighting"]
    sc = roundtrip_meta["SampleCondition"]
    assert pd.api.types.is_string_dtype(sl.dtype)
    assert pd.api.types.is_string_dtype(sc.dtype)
    assert sl.iloc[0] == "Sunlit"
    assert sc.iloc[0] == "Well-hydrated"


def test_validate_required_columns_logs_warning_when_missing(caplog, tmp_path):
    """Missing required Leafweb variables should emit warnings, not raise."""
    fixtures = Path(__file__).parent / "fixtures"
    csv_path = fixtures / "sample_curve.csv"
    if not csv_path.exists():
        pytest.skip("fixture not found")

    backend = FilesystemBackend()
    # Parse normally to get a valid DataFrame, then drop a required column
    _, meas = parse_curve_file(str(csv_path), backend)
    if "AnetCO2" not in meas.columns:
        pytest.skip("sample_curve.csv does not include AnetCO2")

    meas = meas.drop(columns=["AnetCO2"])

    # Reuse convert_curves alignment logic on a manual frame to trigger validation
    with caplog.at_level("WARNING"):
        # Align to standard columns then run through normalize/write to invoke validation indirectly
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        normalize_and_write_parquet(
            pd.DataFrame([{"curve_id": "curve1"}]),
            meas.assign(curve_id="curve1"),
            out_dir,
        )

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "Leafweb required measurement columns are missing or empty for one or more curves" in messages


def _write_leafweb_fixture_with_air_header(tmp_path: Path, air_header: str) -> Path:
    """Create a leafweb-like fixture with a configurable air pressure header."""
    fixtures = Path(__file__).parent / "fixtures"
    source_path = fixtures / "sample_leafweb_updated.csv"
    if not source_path.exists():
        pytest.skip("fixture sample_leafweb_updated.csv not found")

    contents = source_path.read_text(encoding="utf-8")
    contents = contents.replace("!AirPress", air_header)

    out_path = tmp_path / f"leafweb_{air_header.replace('!', '').lower()}.csv"
    out_path.write_text(contents, encoding="utf-8")
    return out_path


def test_required_airpress_not_missing_when_airpres_alias_present(caplog, tmp_path):
    """AirPres should normalize to AirPress before required-column validation."""
    csv_path = _write_leafweb_fixture_with_air_header(tmp_path, "AirPres")
    backend = FilesystemBackend()

    with caplog.at_level("WARNING"):
        _meta, meas = parse_curve_file(str(csv_path), backend)

    assert "AirPress" in meas.columns
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "Leafweb required measurement columns are missing or empty" not in messages


def test_required_airpress_not_missing_when_patm_alias_present(caplog, tmp_path):
    """Patm should normalize to AirPress before required-column validation."""
    csv_path = _write_leafweb_fixture_with_air_header(tmp_path, "Patm")
    backend = FilesystemBackend()

    with caplog.at_level("WARNING"):
        _meta, meas = parse_curve_file(str(csv_path), backend)

    assert "AirPress" in meas.columns
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "Leafweb required measurement columns are missing or empty" not in messages


def test_required_airpress_warning_when_all_airpress_aliases_absent(caplog, tmp_path):
    """Warning should remain when AirPress and all aliases are absent."""
    csv_path = _write_leafweb_fixture_with_air_header(tmp_path, "AirPressureX")
    backend = FilesystemBackend()

    with caplog.at_level("WARNING"):
        _meta, meas = parse_curve_file(str(csv_path), backend)

    assert "AirPress" not in meas.columns
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "Leafweb required measurement columns are missing or empty for one or more curves" in messages
    assert "AirPress" in messages


def test_gfs_cornell_param_headers_alias_to_canonical(tmp_path: Path):
    """All seven GFS/Cornell param names land on the standard metadata keys."""
    fixtures = Path(__file__).parent / "fixtures"
    source = fixtures / "sampleinput.csv"
    if not source.exists():
        pytest.skip("fixture sampleinput.csv not found")

    lines = source.read_text(encoding="utf-8").splitlines()
    param_idx = next(i for i, line in enumerate(lines) if line.startswith("Gamma*"))
    lines[param_idx] = "Gamma*_25oC,Kc_25oC,Ko_25oC,Alpha_25oC,Rd_25oC,rwp_25oC,rch_25oC"
    lines[param_idx + 1] = "Pa,Pa,Pa,NoUnit,umol/m2/s,umol-1m2sPa,umol-1m2sPa"
    lines[param_idx + 2] = "41,42,43,44,45,46,47"

    out = tmp_path / "gfs_params.csv"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    meta, _meas = parse_curve_file(str(out), FilesystemBackend())

    assert meta["param_Gamma"] == 41
    assert meta["param_Kc25"] == 42
    assert meta["param_Ko25"] == 43
    assert meta["param_AlphaTPU"] == 44
    assert meta["param_Rd25"] == 45
    assert meta["param_ResistWP25"] == 46
    assert meta["param_ResistCH25"] == 47
    assert "param_Gamma*_25oC" not in meta
    assert "param_Kc_25oC" not in meta


def test_chamber_area_aliases_to_leaf_area_measured(tmp_path: Path):
    fixtures = Path(__file__).parent / "fixtures"
    source = fixtures / "sampleinput.csv"
    if not source.exists():
        pytest.skip("fixture sampleinput.csv not found")

    lines = source.read_text(encoding="utf-8").splitlines()
    header_idx = next(i for i, line in enumerate(lines) if line.startswith("Obs,"))
    lines[header_idx] = lines[header_idx].replace(",Area,", ",ChamberArea,")
    out = tmp_path / "chamber_area.csv"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    _meta, meas = parse_curve_file(str(out), FilesystemBackend())
    assert "LeafAreaMeasured" in meas.columns
    assert "ChamberArea" not in meas.columns
    assert meas["LeafAreaMeasured"].iloc[0] == 2
