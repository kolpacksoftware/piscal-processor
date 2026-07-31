"""Emit legacy Licor-layout CSVs that the PISCAL Fortran binary reads positionally.

The Fortran parser in ToLeafGasOptimization.f does not use header names for the
data block. It reads fixed positions (e.g. charvars(5)=AdjPhoto, (6)=StomCond,
(23)=PARi). LeafWeb-standard CSVs put those values at different offsets, so this
module rewrites a parsed curve into the 21 / 7 / 38 column legacy shape.

Positions 1-19 (site), 1-6 (parameters), and 1-31 (measurements) are exactly the
order given in docs/inputformat.txt, which is what makes the positional reads
land correctly; test_legacy.py pins that against tests/fixtures/sampleinput.csv.
The columns beyond those are an append-only extension, and emitting them assumes
the binary's format sniffer accepts the wider blocks (site 15-25, parameters
5-10, data >= 25). That range cannot be verified from this repo because
ToLeafGasOptimization.f is not vendored here. See docs/legacy_format.md.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from piscal_processor.parser import (
    next_nonempty,
    normalize_scalar,
    parse_csv_line,
    parse_key_value_section,
    parse_triplet,
)
from piscal_processor.schema import METADATA_COLUMN_ALIASES, MEASUREMENT_COLUMN_ALIASES
from piscal_processor.storage import StorageBackend, get_backend

LOG = logging.getLogger(__name__)

MIN_DATA_ROWS = 4
MISSING = "-9999"

# Descriptive lines 1-10, in the order Leafweb / sampleinput use.
DESCRIPTIVE_KEYS = [
    "Investigator name",
    "Contact information",
    "Site name in full",
    "Vegetation type",
    "Soil type",
    "Major species",
    "Sample leaf light environment",
    "Water stress assessment",
    "Instrument used",
    "Extra info",
]

# 21-column site block matching LeafInput-valid / docs/inputformat.txt.
# Positional reads: SiteID=1, Lat=2, Lon=3, ..., SpeciesSampled=12,
# AveTimeResolution=13, ..., WoodPorosity=20, SapWoodDensity=21.
LEGACY_SITE_COLUMNS = [
    "SiteID",
    "Latitude(Degrees)",
    "Longitude(Degrees)",
    "Elevation",
    "SampleYear",
    "SampleDayOfYear",
    "GrowSeasonStart",
    "GrowSeasonEnd",
    "StandAge",
    "CanopyHeight",
    "LeafAreaIndex",
    "SpeciesSampled",
    "AveTimeResolution",
    "SampleHeight",
    "LeafAge",
    "SpecificLeafArea",
    "LfNitrogenContent",
    "LfCarbonContent",
    "LfPhosphContent",
    "WoodPorosity",
    "SapWoodDensity",
]

LEGACY_SITE_UNITS = [
    "NoUnit",
    "NorthPositive",
    "EastPositive",
    "m",
    "NoUnit",
    "DayOfYear",
    "DayOfYear",
    "DayOfYear",
    "Year",
    "m",
    "m2/m2",
    "NoBlankSpace",
    "Minutes",
    "m",
    "days",
    "cm2/g",
    "%",
    "%",
    "%",
    "NoUnit",
    "g/cm3",
]

# Canonical metadata keys that feed each legacy site column.
_SITE_SOURCE_KEYS = [
    "SiteID",
    "Latitude",
    "Longitude",
    "Elevation",
    "SampleYear",
    "SampleDayOfYear",
    "GrowSeasonStart",
    "GrowSeasonEnd",
    "StandAge",
    "CanopyHeight",
    "LeafAreaIndex",
    "SpeciesSampled",
    "AveTimeResolution",  # usually absent; emitted as -9999
    "SampleHeight",
    "LeafAge",
    "SpecificLeafArea",
    "LfNitrogenContent",
    "LfCarbonContent",
    "LfPhosphorusContent",
    "WoodPorosity",
    "Sapwooddensity",
]

# String-ish site columns (everything else is numeric / -9999).
_SITE_STRING_KEYS = {"SiteID", "SpeciesSampled", "WoodPorosity"}

# 7-column parameter block. Fortran reads positions 1-7 as
# Gamma*, Kc, Ko, Alpha, Rd, ResistWP, ResistCH.
LEGACY_PARAM_COLUMNS = [
    "Gamma*",
    "Kc",
    "Ko",
    "Alpha",
    "Rd",
    "ResistWP25",
    "ResistCH25",
]

LEGACY_PARAM_UNITS = [
    "Pa",
    "Pa",
    "Pa",
    "NoUnit",
    "umol/m2/s",
    "umol/m2/s/Pa",
    "umol/m2/s/Pa",
]

_PARAM_SOURCE_KEYS = [
    "param_Gamma",
    "param_Kc25",
    "param_Ko25",
    "param_AlphaTPU",
    "param_Rd25",
    "param_ResistWP25",
    "param_ResistCH25",
]

# 38-column measurement block matching LeafInput-valid line 17.
LEGACY_MEASUREMENT_COLUMNS = [
    "Obs",
    "HHMMSS",
    "FTime",
    "Photo",
    "!AdjPhoto",
    "!StomCond",
    "!Ci",
    "!Trmmol",
    "!VpdL",
    "Area",
    "StmRat",
    "BLCond",
    "Tair",
    "!Tleaf",
    "TBlk",
    "CO2R",
    "CO2S",
    "H2OR",
    "H2OS",
    "RH_R",
    "RH_S",
    "Flow",
    "!PARi",
    "PARo",
    "Press",
    "CsMch",
    "HsMch",
    "StableF",
    "Status",
    "PhiPS2",
    "OxygenPress",
    "DataType",
    "TissueArea",
    "TissueMass",
    "Fo'_or_Fo",
    "Fm'_or_Fm",
    "Fs",
    "MeasLight",
]

# The OxygenPress unit label reproduces sampleinput.csv ("KPA"), which contradicts
# docs/inputformat.txt ("(Pa)"). The column is only ever passed through, never
# derived, so the emitter does not have to pick a side; resolve this before
# computing the value from OxygenLevel%.
LEGACY_MEASUREMENT_UNITS = [
    "NoUnit",
    "HHMMSS",
    "Second",
    "umol/m2/s",
    "umol/m2/s",
    "mol/m2/s",
    "umol/mol",
    "mmol/m2/s",
    "kPa",
    "cm2",
    "NA",
    "mol/m2/s",
    "oC",
    "oC",
    "oC",
    "umol/mol",
    "umol/mol",
    "mmol/mol",
    "mmol/mol",
    "%",
    "%",
    "umol/s",
    "umol/m2/s",
    "umol/m2/s",
    "Kpa",
    "umol/mol",
    "mmol/mol",
    "NA",
    "NA",
    "NA",
    "KPA",
    "123Flu11_25ACi31_45ALight_9999others",
    "cm2",
    "gram",
    "Arb_Unit",
    "Arb_Unit",
    "Arb_Unit",
    "umolm-2s-1",
]


# Metadata keys the emitter has a home for. Anything else carrying a value is
# reported in the conversion notes rather than dropped silently.
_EMITTED_METADATA_KEYS = (
    set(DESCRIPTIVE_KEYS)
    | set(_SITE_SOURCE_KEYS)
    | set(_PARAM_SOURCE_KEYS)
    | {
        "Photosynthetic pathway",
        # Alias spellings resolved by the _site_values fallbacks.
        "Latitude(Degrees)",
        "Longitude(Degrees)",
        "LfPhosphContent",
        # Bookkeeping added by parse_curve_file, not curve data.
        "curve_id",
        "source_file",
        "measurement_units",
        "parameter_units",
        "pathway_subtype",
    }
)

# Measurement columns parse_curve_file injects; not part of the source data block.
_INJECTED_MEASUREMENT_COLUMNS = {
    "curve_id",
    "SpeciesSampled",
    "Major_species",
    "Photosynthetic_pathway",
    "pathway_subtype",
}


class LegacyConversionError(ValueError):
    """Raised when a curve cannot be rewritten into a valid legacy input."""


@dataclass
class LegacyConversionReport:
    """Summary of a legacy rewrite."""

    source: str
    destination: str
    converted: bool
    data_rows: int = 0
    mass_based: bool = False
    notes: List[str] = field(default_factory=list)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    # NaN without importing pandas/numpy.
    if isinstance(value, float) and value != value:
        return True
    text = str(value).strip()
    if not text:
        return True
    if text.upper() in {"NA", "N/A", "NONE", "NULL"}:
        return True
    if text.startswith("-9999"):
        return True
    return False


def _fmt_scalar(value: Any, *, as_string: bool = False) -> str:
    if _is_missing(value):
        return MISSING
    if as_string:
        return str(value).strip()
    if isinstance(value, bool):
        return MISSING
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return f"{value:.10g}"
    text = str(value).strip()
    if not text:
        return MISSING
    # Prefer a clean numeric rendering when the source stored numbers as text.
    try:
        num = float(text)
    except ValueError:
        return text
    if "." not in text and "e" not in text.lower():
        return str(int(num))
    return f"{num:.10g}"


def _csv_line(fields: Sequence[str]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="")
    writer.writerow(list(fields))
    return buf.getvalue()


def _descriptive_line(key: str, value: Any) -> str:
    text = "" if _is_missing(value) else str(value).strip()
    # Quote the whole "Key: value" when the value contains a comma so the
    # Fortran sniffer sees a single field (matching LeafInput-valid).
    if "," in text:
        return _csv_line([f"{key}: {text}"])
    return f"{key}: {text}" if text else f"{key}: None"


def _site_values(metadata: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    for header, source_key in zip(LEGACY_SITE_COLUMNS, _SITE_SOURCE_KEYS):
        raw = metadata.get(source_key)
        # Aliases may leave the original key when parse_curve_file wasn't
        # reindexed; also accept Latitude(Degrees) etc. as a fallback.
        if _is_missing(raw) and source_key == "Latitude":
            raw = metadata.get("Latitude(Degrees)")
        if _is_missing(raw) and source_key == "Longitude":
            raw = metadata.get("Longitude(Degrees)")
        if _is_missing(raw) and source_key == "LfPhosphorusContent":
            raw = metadata.get("LfPhosphContent")
        # Non-numeric Sapwooddensity (HIGH/LOW) must become -9999: the Fortran
        # reader calls extCharToFloatNum on position 21.
        if source_key == "Sapwooddensity" and not _is_missing(raw):
            try:
                float(str(raw).strip())
            except ValueError:
                raw = None
        values.append(_fmt_scalar(raw, as_string=source_key in _SITE_STRING_KEYS))
    return values


def _param_values(metadata: Dict[str, Any]) -> List[str]:
    return [_fmt_scalar(metadata.get(key)) for key in _PARAM_SOURCE_KEYS]


def _row_lookup(row: Mapping[str, Any], *names: str) -> tuple[Any, Optional[str]]:
    """First present, non-missing value among *names*, with the name that supplied it."""
    for name in names:
        if name in row and not _is_missing(row[name]):
            return row[name], name
    return None, None


def _curve_is_mass_based(measurements: Sequence[Mapping[str, Any]]) -> bool:
    """True when every row that has tissue dims also has mass-recompute inputs.

    Fortran rejects mixed area/mass curves, so the decision is per-curve. Mass
    mode also requires CO2R, H2OR, and Flow because the recompute uses them.
    """
    if not measurements:
        return False
    has_any = False
    for row in measurements:
        area = row.get("TissueArea")
        mass = row.get("TissueMass")
        if _is_missing(area) or _is_missing(mass):
            continue
        try:
            if float(area) <= 0.0 or float(mass) <= 0.0:
                continue
        except (TypeError, ValueError):
            continue
        has_any = True
        for col in ("CO2R", "H2OR", "MainFlowRate"):
            if _is_missing(row.get(col)):
                return False
    return has_any


def _measurement_row(
    row: Mapping[str, Any],
    *,
    obs_fallback: int,
    mass_based: bool,
    consumed: Optional[set] = None,
) -> List[str]:
    """Build one 38-field legacy data row.

    The source column each field is taken from is recorded in *consumed*, so the
    caller can report populated source columns that had nowhere to go. Only the
    winning name is recorded: a column that loses to a higher-priority alias
    really does get dropped.
    """

    def get(*names: str) -> Any:
        value, winner = _row_lookup(row, *names)
        if winner is not None and consumed is not None:
            consumed.add(winner)
        return value

    anet = get("AnetCO2", "!AnetCO2", "!AdjPhoto")
    # Photo is the raw rate and AdjPhoto the leakage-corrected one. Keep them
    # distinct when the source has both; fall back to anet so position 4 is
    # never empty for standard files, which only carry the corrected rate.
    photo = get("Photo")
    if _is_missing(photo):
        photo = anet
    obs = get("ObsNo", "Obs")
    if _is_missing(obs):
        obs = obs_fallback

    tissue_area = MISSING
    tissue_mass = MISSING
    if mass_based:
        tissue_area = _fmt_scalar(get("TissueArea"))
        tissue_mass = _fmt_scalar(get("TissueMass"))
    elif consumed is not None:
        consumed.update(("TissueArea", "TissueMass"))

    return [
        _fmt_scalar(obs),
        _fmt_scalar(get("HHMMSS"), as_string=True),
        _fmt_scalar(get("FTime")),
        _fmt_scalar(photo),
        _fmt_scalar(anet),
        _fmt_scalar(get("StomCond", "!StomCond")),
        _fmt_scalar(get("CO2i", "!CO2i", "!Ci", "Ci")),
        _fmt_scalar(get("Trmmol", "!Trmmol")),
        _fmt_scalar(get("VpdL", "!VpdL")),
        _fmt_scalar(get("LeafAreaMeasured", "Area")),
        _fmt_scalar(get("StmRat")),
        _fmt_scalar(get("BLCond")),
        _fmt_scalar(get("Tair")),
        _fmt_scalar(get("Tleaf", "!Tleaf")),
        _fmt_scalar(get("TBlk")),
        _fmt_scalar(get("CO2R")),
        _fmt_scalar(get("CO2S")),
        _fmt_scalar(get("H2OR")),
        _fmt_scalar(get("H2OS")),
        _fmt_scalar(get("RH_R")),
        _fmt_scalar(get("RH_S")),
        _fmt_scalar(get("MainFlowRate", "Flow")),
        _fmt_scalar(get("PARi", "!PARi")),
        _fmt_scalar(get("PARo")),
        _fmt_scalar(get("AirPress", "!AirPress", "Press", "AirPres", "Patm")),
        _fmt_scalar(get("CsMch")),
        _fmt_scalar(get("HsMch")),
        _fmt_scalar(get("StableF")),
        _fmt_scalar(get("Status")),
        _fmt_scalar(get("PhiPSII", "PhiPS2")),
        # Passed through only when the source already states a partial pressure.
        # It is never derived from OxygenLevel%: see docs/legacy_format.md for the
        # unresolved Pa vs kPa conflict between inputformat.txt and sampleinput.csv.
        _fmt_scalar(get("OxygenPress")),
        _fmt_scalar(get("DataType")),
        tissue_area,
        tissue_mass,
        _fmt_scalar(get("FoOrFsp", "Fo'_or_Fo", "!FoorFs'", "FoDark")),
        _fmt_scalar(get("FmOrFmp", "Fm'_or_Fm", "!FmorFm'", "FmDark")),
        _fmt_scalar(get("Fs")),
        _fmt_scalar(get("MeasLight")),
    ]


def _measurement_header_index(lines: List[str], source_label: str) -> int:
    """Index of the measurement header line, past the site and parameter blocks."""
    try:
        idx, _ = parse_key_value_section(lines)
        idx, _, _, _ = parse_triplet(lines, idx)  # site
        idx, _, _, _ = parse_triplet(lines, idx)  # params
        return next_nonempty(lines, idx)
    except IndexError as exc:
        raise LegacyConversionError(
            f"{source_label}: not a PISCAL CSV; expected descriptive lines followed "
            "by site and parameter header/units/values blocks"
        ) from exc


def needs_legacy_conversion(
    src: Union[str, Path],
    backend: Optional[StorageBackend] = None,
    *,
    text: Optional[str] = None,
) -> bool:
    """Return True when the file's measurement header is not already legacy.

    Raises LegacyConversionError when *src* is not a PISCAL CSV at all. Pass
    *text* to reuse content already read from *src*.
    """
    backend = backend or get_backend(str(src))
    if text is None:
        text = backend.read_text(src)
    lines = text.splitlines()
    idx = _measurement_header_index(lines, str(src))
    if idx >= len(lines):
        return True
    headers = [h.strip() for h in parse_csv_line(lines[idx])]
    if not headers:
        return True
    first = headers[0]
    has_adj = any(h in {"!AdjPhoto", "AdjPhoto"} for h in headers)
    return not (first == "Obs" and has_adj)


def _count_data_rows(text: str, source_label: str) -> int:
    """Number of non-empty data rows below the measurement header and units lines."""
    lines = text.splitlines()
    idx = _measurement_header_index(lines, source_label)
    idx = next_nonempty(lines, idx + 1)  # units line
    return sum(1 for line in lines[idx + 1 :] if line.strip())


def _parse_curve_plain(
    text: str, source_label: str
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Parse a PISCAL CSV into metadata + measurement row dicts (no pandas)."""
    lines = text.splitlines()
    try:
        idx, general_info = parse_key_value_section(lines)
        idx, site_headers, _site_units, site_values = parse_triplet(lines, idx)
        idx, param_headers, _param_units, param_values = parse_triplet(lines, idx)
        idx = next_nonempty(lines, idx)
        measurement_headers = parse_csv_line(lines[idx])
        idx += 1
        idx = next_nonempty(lines, idx)
        _measurement_units = parse_csv_line(lines[idx])
        idx += 1
    except IndexError as exc:
        raise LegacyConversionError(
            f"{source_label}: not a PISCAL CSV; expected descriptive lines followed "
            "by site, parameter, and measurement blocks"
        ) from exc

    site_data = {
        header.strip(): normalize_scalar(value)
        for header, value in zip(site_headers, site_values)
    }
    param_data = {
        f"param_{header.strip()}": normalize_scalar(value)
        for header, value in zip(param_headers, param_values)
    }
    metadata: Dict[str, Any] = {**general_info, **site_data, **param_data}
    for alias, canonical in METADATA_COLUMN_ALIASES.items():
        if alias in metadata and canonical not in metadata:
            metadata[canonical] = metadata.pop(alias)
        elif alias in metadata:
            metadata.pop(alias)

    headers = [h.strip() for h in measurement_headers]
    aliased = [MEASUREMENT_COLUMN_ALIASES.get(h, h) for h in headers]
    rows: List[Dict[str, Any]] = []
    while idx < len(lines):
        line = lines[idx]
        idx += 1
        if not line.strip():
            continue
        fields = parse_csv_line(line)
        if not fields:
            continue
        if len(fields) < len(aliased):
            fields = fields + [""] * (len(aliased) - len(fields))
        row: Dict[str, Any] = {}
        for name, raw in zip(aliased, fields):
            # Keep the first spelling when two headers alias to the same name.
            if name in row and not _is_missing(row[name]):
                continue
            row[name] = normalize_scalar(raw)
        rows.append(row)
    return metadata, rows


def _as_row_mappings(measurements: Any) -> List[Mapping[str, Any]]:
    """Normalize a DataFrame or sequence of mappings into list[Mapping]."""
    if hasattr(measurements, "to_dict") and hasattr(measurements, "columns"):
        # pandas DataFrame: avoid truthiness checks on the frame itself.
        return measurements.to_dict(orient="records")
    return list(measurements)


def to_legacy_text(
    metadata: Dict[str, Any],
    measurements: Sequence[Mapping[str, Any]],
    *,
    source_label: str = "<memory>",
) -> tuple[str, LegacyConversionReport]:
    """Render canonical metadata + measurement rows as a legacy CSV string."""
    rows = _as_row_mappings(measurements)
    n_rows = len(rows)
    if n_rows < MIN_DATA_ROWS:
        raise LegacyConversionError(
            f"{source_label}: need at least {MIN_DATA_ROWS} data rows for the "
            f"Fortran format sniffer, found {n_rows}"
        )

    notes: List[str] = []
    mass_based = _curve_is_mass_based(rows)
    if not mass_based:
        notes.append(
            "TissueArea/TissueMass emitted as -9999 "
            "(missing dims or mass-recompute inputs)"
        )

    lines: List[str] = []
    # The legacy layout has exactly 10 descriptive lines and no slot for the
    # pathway, so fold C3/C4 into Extra info rather than losing it.
    descriptive = {key: metadata.get(key) for key in DESCRIPTIVE_KEYS}
    pathway = metadata.get("Photosynthetic pathway")
    if not _is_missing(pathway):
        extra = descriptive.get("Extra info")
        pathway_text = f"Photosynthetic pathway: {str(pathway).strip()}"
        descriptive["Extra info"] = (
            pathway_text if _is_missing(extra) else f"{str(extra).strip()}; {pathway_text}"
        )
    for key in DESCRIPTIVE_KEYS:
        lines.append(_descriptive_line(key, descriptive[key]))

    lines.append(_csv_line(LEGACY_SITE_COLUMNS))
    lines.append(_csv_line(LEGACY_SITE_UNITS))
    lines.append(_csv_line(_site_values(metadata)))

    lines.append(_csv_line(LEGACY_PARAM_COLUMNS))
    lines.append(_csv_line(LEGACY_PARAM_UNITS))
    lines.append(_csv_line(_param_values(metadata)))

    lines.append(_csv_line(LEGACY_MEASUREMENT_COLUMNS))
    lines.append(_csv_line(LEGACY_MEASUREMENT_UNITS))
    consumed: set = set()
    data_fields: List[List[str]] = []
    for i, row in enumerate(rows, start=1):
        fields = _measurement_row(
            row, obs_fallback=i, mass_based=mass_based, consumed=consumed
        )
        if len(fields) != len(LEGACY_MEASUREMENT_COLUMNS):
            raise LegacyConversionError(
                f"internal error: expected {len(LEGACY_MEASUREMENT_COLUMNS)} fields, "
                f"got {len(fields)}"
            )
        data_fields.append(fields)
        lines.append(_csv_line(fields))

    all_missing = [
        name
        for j, name in enumerate(LEGACY_MEASUREMENT_COLUMNS)
        if all(fields[j] == MISSING for fields in data_fields)
    ]
    if all_missing:
        notes.append("emitted as -9999 for every row: " + ", ".join(all_missing))

    source_columns = {str(col) for row in rows for col in row}
    dropped_measurements = sorted(
        col
        for col in source_columns
        if col not in consumed
        and col not in _INJECTED_MEASUREMENT_COLUMNS
        and any(not _is_missing(row.get(col)) for row in rows)
    )
    if dropped_measurements:
        notes.append(
            "source measurement columns with no legacy slot: "
            + ", ".join(dropped_measurements)
        )

    dropped_metadata = sorted(
        str(key)
        for key, value in metadata.items()
        if str(key) not in _EMITTED_METADATA_KEYS and not _is_missing(value)
    )
    if dropped_metadata:
        notes.append(
            "source metadata fields with no legacy slot: " + ", ".join(dropped_metadata)
        )

    report = LegacyConversionReport(
        source=source_label,
        destination="",
        converted=True,
        data_rows=n_rows,
        mass_based=mass_based,
        notes=notes,
    )
    return "\n".join(lines) + "\n", report


def write_legacy_input(
    src: Union[str, Path],
    dest: Union[str, Path],
    *,
    backend: Optional[StorageBackend] = None,
    force: bool = False,
) -> LegacyConversionReport:
    """Parse *src* and write a legacy-format CSV to *dest*.

    When the source is already legacy and *force* is False, the file is copied
    through unchanged and ``converted`` is False.

    Raises LegacyConversionError when *src* is not a PISCAL CSV or has too few
    data rows for the Fortran format sniffer. Nothing is written on failure.

    Parsing is pandas-free so the API cleaning path does not load pyarrow.
    """
    backend = backend or get_backend(str(src))
    src_s = str(src)
    dest_s = str(dest)
    # Read once: both the dialect check and the parse work from this text.
    source_text = backend.read_text(src_s)

    if not force and not needs_legacy_conversion(src_s, backend, text=source_text):
        n_rows = _count_data_rows(source_text, src_s)
        if n_rows < MIN_DATA_ROWS:
            raise LegacyConversionError(
                f"{src_s}: need at least {MIN_DATA_ROWS} data rows for the "
                f"Fortran format sniffer, found {n_rows}"
            )
        backend.ensure_output_parent(dest_s)
        backend.write_text(
            dest_s, source_text if source_text.endswith("\n") else source_text + "\n"
        )
        return LegacyConversionReport(
            source=src_s,
            destination=dest_s,
            converted=False,
            data_rows=n_rows,
            notes=["already legacy; copied unchanged"],
        )

    metadata, measurements = _parse_curve_plain(source_text, src_s)
    text, report = to_legacy_text(metadata, measurements, source_label=src_s)
    report.destination = dest_s
    backend.ensure_output_parent(dest_s)
    backend.write_text(dest_s, text)
    LOG.info(
        "Wrote legacy input %s -> %s (%d rows, mass_based=%s)",
        src_s,
        dest_s,
        report.data_rows,
        report.mass_based,
    )
    return report
