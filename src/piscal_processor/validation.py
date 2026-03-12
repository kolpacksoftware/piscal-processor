"""Lightweight validation helpers for PISCAL-format CSV files.

These functions perform structural checks on a CSV file to decide whether it
looks like a valid PISCAL / Leafweb curve file. They are intentionally cheaper
than a full parse into DataFrames and are suitable for quick CLI or preflight
checks.
"""

from __future__ import annotations

from pathlib import Path
from typing import IO, Iterable, List, Tuple, Union

from piscal_processor.parser import (
    next_nonempty,
    parse_csv_line,
    parse_key_value_section,
    parse_triplet,
)
from piscal_processor.schema import MEASUREMENT_COLUMN_ALIASES


StrOrPath = Union[str, Path]


def _read_lines(path_or_buffer: Union[StrOrPath, IO[str]]) -> List[str]:
    """Read text lines from a filesystem path or a text-mode file object."""
    if isinstance(path_or_buffer, (str, Path)):
        with open(path_or_buffer, "r", encoding="utf-8") as f:  # type: ignore[arg-type]
            return f.read().splitlines()
    # Assume file-like object already opened in text mode
    text = path_or_buffer.read()
    return text.splitlines()


def _normalize_headers(headers: Iterable[str]) -> List[str]:
    """Trim whitespace from header names."""
    return [h.strip() for h in headers]


def validate_piscal_csv(
    path_or_buffer: Union[StrOrPath, IO[str]],
    *,
    strict: bool = False,
) -> Tuple[bool, List[str]]:
    """Validate that a CSV file appears to follow the PISCAL/Leafweb format.

    The validator performs structural checks based on the documented format:
    - Descriptive key/value header section
    - Site triplet (headers/units/values)
    - Parameter triplet (legacy or Leafweb-style names)
    - Measurement table (headers, units, and at least one data row)

    Args:
        path_or_buffer: Filesystem path or text-mode file-like object.
        strict: Reserved for future tightening of rules; currently both modes
            apply the same checks but callers can opt into stricter behavior
            once extended.

    Returns:
        Tuple of (is_valid, errors). When is_valid is False, errors contains
        one or more human-readable messages describing why validation failed.
    """
    errors: List[str] = []

    try:
        lines = _read_lines(path_or_buffer)
    except OSError as exc:  # pragma: no cover - OS-specific failures
        return False, [f"Failed to read file: {exc}"]

    if not lines:
        return False, ["File is empty"]

    # 1) Parse the key/value header section.
    idx, header_info = parse_key_value_section(lines)
    if not header_info:
        errors.append("Missing descriptive header key/value section")
        return False, errors

    # Heuristic: require at least a few header lines to avoid trivial matches.
    if len(header_info) < 3:
        errors.append("Too few header key/value lines for PISCAL format")
        return False, errors

    # 2) Site triplet: headers/units/values.
    try:
        idx, site_headers, _site_units, _site_values = parse_triplet(lines, idx)
    except Exception:
        errors.append("Failed to parse site triplet (headers/units/values)")
        return False, errors

    site_headers_norm = set(_normalize_headers(site_headers))
    expected_site_any = {
        "SiteID",
        "SpeciesSampled",
        "SampleYear",
        "Latitude(Degrees)",
        "Latitude",
    }
    if not site_headers_norm.intersection(expected_site_any):
        errors.append("Site header row missing expected PISCAL/Leafweb columns")
        return False, errors

    # 3) Parameter triplet: legacy or Leafweb-style names.
    try:
        idx, param_headers, _param_units, _param_values = parse_triplet(lines, idx)
    except Exception:
        errors.append("Failed to parse parameter triplet (headers/units/values)")
        return False, errors

    param_headers_norm = set(_normalize_headers(param_headers))
    legacy_params = {"Gamma", "Kc", "Ko", "Alpha", "Rd", "gi"}
    leafweb_params = {
        "Gamma*25",
        "KC25",
        "KO25",
        "AlphaTPU",
        "Rd25",
        "Resistwpbs25",
        "Resistchm25",
    }
    if not (param_headers_norm.intersection(legacy_params) or param_headers_norm.intersection(leafweb_params)):
        errors.append("Parameter header row missing legacy or Leafweb parameter names")
        return False, errors

    # 4) Measurement table: headers, units, and at least one data row.
    idx = next_nonempty(lines, idx)
    if idx >= len(lines):
        errors.append("Missing measurement header row")
        return False, errors

    measurement_headers = _normalize_headers(parse_csv_line(lines[idx]))
    idx += 1

    idx = next_nonempty(lines, idx)
    if idx >= len(lines):
        errors.append("Missing measurement units row")
        return False, errors
    measurement_units = parse_csv_line(lines[idx])
    if len(measurement_units) != len(measurement_headers):
        errors.append("Measurement units row has different column count than headers")
        return False, errors
    idx += 1

    # At least one non-empty data row, with a reasonable column count.
    data_rows = 0
    while idx < len(lines):
        line = lines[idx]
        idx += 1
        if not line.strip():
            continue
        row = parse_csv_line(line)
        if len(row) != len(measurement_headers):
            # Column mismatches are strongly indicative of a non-PISCAL file.
            errors.append("Measurement data row has different column count than headers")
            return False, errors
        data_rows += 1
        break

    if data_rows == 0:
        errors.append("No measurement data rows found")
        return False, errors

    # Check for presence of expected measurement columns, accounting for aliases.
    header_set = set(measurement_headers)
    normalized_headers = set(measurement_headers)
    for name in list(header_set):
        if name in MEASUREMENT_COLUMN_ALIASES:
            normalized_headers.add(MEASUREMENT_COLUMN_ALIASES[name])

    required_any_timing = {"DataType", "Obs", "ObsNo"}
    if not normalized_headers.intersection(required_any_timing):
        errors.append("Measurement headers missing timing/control columns (DataType/Obs/ObsNo)")
        return False, errors

    required_any_gas_exchange = {
        "AnetCO2",
        "PARi",
        "Tleaf",
        "CO2i",
    }
    if not normalized_headers.intersection(required_any_gas_exchange):
        errors.append("Measurement headers missing key gas-exchange columns")
        return False, errors

    return True, []


def is_piscal_csv(
    path_or_buffer: Union[StrOrPath, IO[str]],
    *,
    strict: bool = False,
) -> bool:
    """Return True if the file appears to be in PISCAL/Leafweb CSV format."""
    ok, _ = validate_piscal_csv(path_or_buffer, strict=strict)
    return ok

