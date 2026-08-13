"""Tests for legacy Licor-layout emission."""

from __future__ import annotations

from pathlib import Path

import pytest

from piscal_processor.converter import parse_curve_file
from piscal_processor.legacy import (
    LEGACY_MEASUREMENT_COLUMNS,
    LEGACY_MEASUREMENT_UNITS,
    LEGACY_PARAM_COLUMNS,
    LEGACY_PARAM_UNITS,
    LEGACY_SITE_COLUMNS,
    LEGACY_SITE_UNITS,
    LegacyConversionError,
    needs_legacy_conversion,
    to_legacy_text,
    write_legacy_input,
)
from piscal_processor.parser import parse_csv_line, parse_key_value_section, parse_triplet
from piscal_processor.storage import get_backend

FIXTURES = Path(__file__).parent / "fixtures"
STANDARD_4 = FIXTURES / "sample_standard_4rows.csv"
STANDARD_2 = FIXTURES / "sample_leafweb_updated.csv"
LEGACY = FIXTURES / "sampleinput.csv"


def _block_widths(path: Path) -> tuple[int, int, int, int]:
    """Return (site_n, param_n, meas_n, data_rows)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    idx, _ = parse_key_value_section(lines)
    idx, site_h, site_u, site_v = parse_triplet(lines, idx)
    assert len(site_h) == len(site_u) == len(site_v)
    idx, param_h, param_u, param_v = parse_triplet(lines, idx)
    assert len(param_h) == len(param_u) == len(param_v)
    from piscal_processor.parser import next_nonempty

    idx = next_nonempty(lines, idx)
    meas_h = parse_csv_line(lines[idx])
    idx += 1
    idx = next_nonempty(lines, idx)
    meas_u = parse_csv_line(lines[idx])
    idx += 1
    assert len(meas_h) == len(meas_u)
    data_rows = 0
    while idx < len(lines):
        if not lines[idx].strip():
            idx += 1
            continue
        row = parse_csv_line(lines[idx])
        # Trailing empties discarded the same way Fortran does for comparison.
        while row and row[-1] == "":
            row.pop()
        assert len(row) == len(meas_h), (idx, len(row), len(meas_h))
        data_rows += 1
        idx += 1
    return len(site_h), len(param_h), len(meas_h), data_rows


def test_needs_legacy_conversion_detects_dialects():
    assert needs_legacy_conversion(STANDARD_4) is True
    assert needs_legacy_conversion(LEGACY) is False


def test_write_legacy_emits_21_7_38_shape(tmp_path: Path):
    dest = tmp_path / "out.csv"
    report = write_legacy_input(STANDARD_4, dest)
    assert report.converted is True
    assert report.data_rows == 4
    site_n, param_n, meas_n, data_rows = _block_widths(dest)
    assert site_n == len(LEGACY_SITE_COLUMNS) == 21
    assert param_n == len(LEGACY_PARAM_COLUMNS) == 7
    assert meas_n == len(LEGACY_MEASUREMENT_COLUMNS) == 38
    assert data_rows == 4


def test_write_legacy_round_trip_required_columns(tmp_path: Path):
    dest = tmp_path / "out.csv"
    write_legacy_input(STANDARD_4, dest)

    backend = get_backend(str(STANDARD_4))
    src_meta, src_meas = parse_curve_file(str(STANDARD_4), backend)
    out_meta, out_meas = parse_curve_file(str(dest), backend)

    assert out_meta["SpeciesSampled"] == src_meta["SpeciesSampled"]
    # parse_curve_file aliases Latitude(Degrees) onto Latitude; legacy still emits the on-disk name.
    src_lat = src_meta.get("Latitude", src_meta.get("Latitude(Degrees)"))
    out_lat = out_meta.get("Latitude", out_meta.get("Latitude(Degrees)"))
    assert float(out_lat) == pytest.approx(float(src_lat))
    assert float(out_meta.get("param_Gamma", out_meta.get("param_Gamma*"))) == pytest.approx(
        42.0
    )

    # Emitter writes AnetCO2 into Photo and !AdjPhoto; aliases map !AdjPhoto -> AnetCO2.
    assert list(out_meas["AnetCO2"]) == list(src_meas["AnetCO2"])
    assert list(out_meas["StomCond"]) == list(src_meas["StomCond"])
    assert list(out_meas["CO2i"]) == list(src_meas["CO2i"])
    assert list(out_meas["PARi"]) == list(src_meas["PARi"])
    assert list(out_meas["Tleaf"]) == list(src_meas["Tleaf"])
    assert list(out_meas["AirPress"]) == list(src_meas["AirPress"])
    assert list(out_meas["DataType"]) == list(src_meas["DataType"])


def test_write_legacy_refuses_under_four_rows(tmp_path: Path):
    dest = tmp_path / "out.csv"
    with pytest.raises(LegacyConversionError, match="at least 4 data rows"):
        write_legacy_input(STANDARD_2, dest)
    assert not dest.exists()


def test_write_legacy_idempotent_for_legacy_input(tmp_path: Path):
    dest = tmp_path / "out.csv"
    report = write_legacy_input(LEGACY, dest)
    assert report.converted is False
    assert dest.read_text(encoding="utf-8") == LEGACY.read_text(encoding="utf-8")


def test_write_legacy_force_rewrites_legacy(tmp_path: Path):
    dest = tmp_path / "out.csv"
    report = write_legacy_input(LEGACY, dest, force=True)
    assert report.converted is True
    site_n, param_n, meas_n, data_rows = _block_widths(dest)
    assert (site_n, param_n, meas_n) == (21, 7, 38)
    assert data_rows >= 4


def _blocks(path: Path):
    """Return (site, param, measurement) as (headers, units) pairs."""
    lines = path.read_text(encoding="utf-8").splitlines()
    idx, _ = parse_key_value_section(lines)
    idx, site_h, site_u, _ = parse_triplet(lines, idx)
    idx, param_h, param_u, _ = parse_triplet(lines, idx)
    from piscal_processor.parser import next_nonempty

    idx = next_nonempty(lines, idx)
    meas_h = parse_csv_line(lines[idx])
    idx = next_nonempty(lines, idx + 1)
    meas_u = parse_csv_line(lines[idx])
    return (site_h, site_u), (param_h, param_u), (meas_h, meas_u)


def test_emitted_columns_match_spec_positions():
    """The binary reads by position, so positions 1-19 / 1-6 / 1-31 must match the spec.

    sampleinput.csv is the reference layout from docs/inputformat.txt. Anything the
    emitter adds beyond those counts is an append-only extension; if it ever shifts
    an earlier column, the Fortran reads land on the wrong variable.
    """
    (site_h, site_u), (param_h, param_u), (meas_h, meas_u) = _blocks(LEGACY)
    assert (len(site_h), len(param_h), len(meas_h)) == (19, 6, 31)

    assert LEGACY_SITE_COLUMNS[: len(site_h)] == site_h
    assert LEGACY_SITE_UNITS[: len(site_u)] == site_u

    # Position 6 is the same quantity under a newer name: the spec calls it gi
    # (internal conductance, umol/m2/s/Pa), the standard schema calls it ResistWP25.
    assert LEGACY_PARAM_COLUMNS[:5] == param_h[:5]
    assert LEGACY_PARAM_COLUMNS[5] == "ResistWP25" and param_h[5] == "gi"
    assert LEGACY_PARAM_UNITS[: len(param_u)] == param_u

    assert LEGACY_MEASUREMENT_COLUMNS[: len(meas_h)] == meas_h
    assert LEGACY_MEASUREMENT_UNITS[: len(meas_u)] == meas_u


def test_converted_output_keeps_spec_positions(tmp_path: Path):
    dest = tmp_path / "out.csv"
    write_legacy_input(STANDARD_4, dest)
    (_, _), (_, _), (meas_h, _) = _blocks(dest)
    (_, _), (_, _), (ref_h, _) = _blocks(LEGACY)
    assert meas_h[: len(ref_h)] == ref_h


def test_force_rewrite_preserves_legacy_only_columns(tmp_path: Path):
    """Columns outside the standard schema must survive a force rewrite."""
    dest = tmp_path / "out.csv"
    write_legacy_input(LEGACY, dest, force=True)

    src_lines = LEGACY.read_text(encoding="utf-8").splitlines()
    dst_lines = dest.read_text(encoding="utf-8").splitlines()
    src_h = parse_csv_line(src_lines[16])
    dst_h = parse_csv_line(dst_lines[16])

    for offset in range(len(src_lines) - 18):
        src_row = dict(zip(src_h, parse_csv_line(src_lines[18 + offset])))
        dst_row = dict(zip(dst_h, parse_csv_line(dst_lines[18 + offset])))
        for column in ("FTime", "CsMch", "HsMch", "StableF", "Status", "Photo"):
            assert float(dst_row[column]) == pytest.approx(float(src_row[column])), column
        assert dst_row["HHMMSS"] == src_row["HHMMSS"]
        # Photo is the raw rate, !AdjPhoto the leakage-corrected one: not the same value.
        assert dst_row["Photo"] != dst_row["!AdjPhoto"]


def test_fluorescence_columns_are_mapped(tmp_path: Path):
    dest = tmp_path / "out.csv"
    write_legacy_input(STANDARD_4, dest)
    _, src_meas = parse_curve_file(str(STANDARD_4), get_backend(str(STANDARD_4)))

    lines = dest.read_text(encoding="utf-8").splitlines()
    row = dict(zip(parse_csv_line(lines[16]), parse_csv_line(lines[18])))
    assert float(row["Fo'_or_Fo"]) == pytest.approx(float(src_meas["FoOrFsp"].iloc[0]))
    assert float(row["Fm'_or_Fm"]) == pytest.approx(float(src_meas["FmOrFmp"].iloc[0]))


def test_mass_based_curve_passes_tissue_dimensions(tmp_path: Path):
    """The fixture has zero tissue dims, so give it real ones to reach the mass path."""
    lines = STANDARD_4.read_text(encoding="utf-8").splitlines()
    header = parse_csv_line(lines[17])
    area_i = header.index("TissueArea")
    mass_i = header.index("TissueMass")
    for i in range(18, len(lines)):
        fields = lines[i].split(",")
        fields[area_i] = "6.0"
        fields[mass_i] = "0.12"
        lines[i] = ",".join(fields)
    source = tmp_path / "mass.csv"
    source.write_text("\n".join(lines) + "\n", encoding="utf-8")

    dest = tmp_path / "out.csv"
    report = write_legacy_input(source, dest)
    assert report.mass_based is True

    out_lines = dest.read_text(encoding="utf-8").splitlines()
    row = dict(zip(parse_csv_line(out_lines[16]), parse_csv_line(out_lines[18])))
    assert float(row["TissueArea"]) == pytest.approx(6.0)
    assert float(row["TissueMass"]) == pytest.approx(0.12)


def test_photosynthetic_pathway_survives_in_extra_info(tmp_path: Path):
    dest = tmp_path / "out.csv"
    write_legacy_input(STANDARD_4, dest)
    _, info = parse_key_value_section(dest.read_text(encoding="utf-8").splitlines())
    # The legacy layout has no pathway line, so C3/C4 rides along in Extra info.
    assert "Photosynthetic pathway: C3" in info["Extra info"]


def test_report_notes_list_dropped_columns(tmp_path: Path):
    report = write_legacy_input(STANDARD_4, tmp_path / "out.csv")
    notes = " | ".join(report.notes)
    assert "ObsDate" in notes
    assert "OxygenLevel" in notes
    assert "SiteEnvironment" in notes
    # FoDark loses to FoOrFsp, so it is genuinely dropped and must be reported.
    assert "FoDark" in notes


def test_conversion_is_idempotent(tmp_path: Path):
    """Converted output must itself read as legacy, or re-running the tool re-mangles it."""
    once = tmp_path / "once.csv"
    write_legacy_input(STANDARD_4, once)
    assert needs_legacy_conversion(once) is False

    twice = tmp_path / "twice.csv"
    report = write_legacy_input(once, twice)
    assert report.converted is False
    assert twice.read_text(encoding="utf-8") == once.read_text(encoding="utf-8")


def test_extra_info_with_commas_survives_round_trip(tmp_path: Path):
    """A comma in a descriptive value must stay one field, and keep the pathway."""
    source = tmp_path / "commas.csv"
    source.write_text(
        STANDARD_4.read_text(encoding="utf-8").replace(
            "Extra info: Leafweb-style header names for legacy conversion tests",
            "Extra info: site A, plot 3, north slope",
        ),
        encoding="utf-8",
    )

    dest = tmp_path / "out.csv"
    write_legacy_input(source, dest)
    _, info = parse_key_value_section(dest.read_text(encoding="utf-8").splitlines())
    assert info["Extra info"] == "site A, plot 3, north slope; Photosynthetic pathway: C3"


def test_passthrough_reports_actual_row_count(tmp_path: Path):
    report = write_legacy_input(LEGACY, tmp_path / "out.csv")
    assert report.converted is False
    assert report.data_rows == 13


@pytest.mark.parametrize("content", ["a,b\n1,2\n", "", "   \n\n"])
@pytest.mark.parametrize("force", [False, True])
def test_non_piscal_input_raises_conversion_error(tmp_path: Path, content: str, force: bool):
    source = tmp_path / "bad.csv"
    source.write_text(content, encoding="utf-8")
    dest = tmp_path / "out.csv"

    with pytest.raises(LegacyConversionError, match="not a PISCAL CSV"):
        write_legacy_input(source, dest, force=force)
    assert not dest.exists()


def test_needs_legacy_conversion_rejects_non_piscal(tmp_path: Path):
    source = tmp_path / "bad.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(LegacyConversionError, match="not a PISCAL CSV"):
        needs_legacy_conversion(source)


def test_legacy_source_with_too_few_rows_is_refused(tmp_path: Path):
    lines = LEGACY.read_text(encoding="utf-8").splitlines()
    short = tmp_path / "short.csv"
    short.write_text("\n".join(lines[:20]) + "\n", encoding="utf-8")

    dest = tmp_path / "out.csv"
    with pytest.raises(LegacyConversionError, match="at least 4 data rows"):
        write_legacy_input(short, dest)
    assert not dest.exists()


def test_to_legacy_text_renders_without_touching_disk():
    backend = get_backend(str(STANDARD_4))
    metadata, measurements = parse_curve_file(str(STANDARD_4), backend)
    text, report = to_legacy_text(metadata, measurements, source_label="in-memory")

    assert report.source == "in-memory"
    assert report.data_rows == 4
    assert text.endswith("\n")
    assert len(parse_csv_line(text.splitlines()[16])) == len(LEGACY_MEASUREMENT_COLUMNS)


def test_cli_to_legacy(tmp_path: Path):
    from piscal_processor.cli import to_legacy_main

    dest = tmp_path / "out.csv"
    import sys

    argv = ["piscal-processor-to-legacy", str(STANDARD_4), "-o", str(dest)]
    old = sys.argv
    try:
        sys.argv = argv
        to_legacy_main()
    finally:
        sys.argv = old
    assert dest.is_file()
    assert _block_widths(dest)[2] == 38
