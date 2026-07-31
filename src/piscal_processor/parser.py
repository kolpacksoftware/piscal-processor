"""Shared parsing functions for PISCAL CSV format files (piscal-processor package)."""

from __future__ import annotations

import csv
from typing import Dict, List, Optional, Tuple

# Missing value indicators used in PISCAL format
MISSING_TOKENS = {"", "NA", "N/A", "NONE", "NULL"}


def parse_csv_line(line: str) -> List[str]:
    """
    Parse a CSV line into a list of fields, handling quoted values and trimming whitespace.

    Uses Python's csv.reader to properly handle quoted fields and commas within quotes.
    The skipinitialspace parameter trims leading whitespace from each field.

    Args:
        line: A single line of CSV text to parse.

    Returns:
        List of string fields extracted from the CSV line.
    """
    return next(csv.reader([line], skipinitialspace=True))


def next_nonempty(lines: List[str], start_idx: int) -> int:
    """
    Find the index of the next non-empty line in a list of strings.

    Skips over blank lines (whitespace-only) starting from start_idx.
    Useful for navigating CSV files that may have inconsistent blank line spacing.

    Args:
        lines: List of strings representing file lines.
        start_idx: Index to start searching from (inclusive).

    Returns:
        Index of the first non-empty line, or len(lines) if all remaining lines are empty.
    """
    idx = start_idx
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    return idx


def normalize_scalar(value: str):
    """
    Convert a string value to an appropriate Python type, handling missing data markers.

    Converts missing value indicators (empty strings, "NA", "-9999") to None.
    Attempts to convert numeric strings to int or float, preserving the original
    representation when possible (int if no decimal point or scientific notation).
    Non-numeric strings are returned as-is.

    Args:
        value: String value to normalize.

    Returns:
        None for missing values, int/float for numeric strings, or the original string.
    """
    # Some exports pad fixed-width fields with NUL bytes rather than spaces.
    text = value.replace("\x00", "").strip()
    if not text:
        return None
    if text.upper() in MISSING_TOKENS:
        return None
    if text.startswith("-9999"):
        return None
    try:
        num = float(text)
        if "." not in text and "e" not in text.lower():
            return int(num)
        return num
    except ValueError:
        return text


def parse_key_value_section(lines: List[str]) -> Tuple[int, Dict[str, Optional[str]]]:
    """
    Parse the descriptive header section (lines 1-11) containing key-value pairs.

    Extracts metadata like "Photosynthetic pathway: C3" or "Investigator name: ..."
    from the beginning of the CSV file. Stops when it encounters the "SiteID" line
    which marks the start of the structured data blocks.

    Args:
        lines: List of all lines from the CSV file.

    Returns:
        Tuple of (next_line_index, dictionary_of_parsed_key_value_pairs). Values that
        are only a missing-value marker are stored as None. The index points to the
        line where parsing stopped (the "SiteID" line).
    """
    idx = 0
    info: Dict[str, Optional[str]] = {}
    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()
        if not stripped:
            idx += 1
            continue
        if stripped.startswith("SiteID"):
            break
        if stripped.startswith('"'):
            # The whole line is one CSV-quoted field because the value contains
            # commas; without this both the key and the value keep a stray quote.
            fields = parse_csv_line(stripped)
            if fields:
                stripped = fields[0]
        if ":" in stripped:
            key, value = stripped.split(":", 1)
            # Strip whitespace, NUL padding, and trailing commas (common CSV artifacts)
            cleaned_value = value.replace("\x00", "").strip().rstrip(",").strip()
            info[key.strip()] = None if cleaned_value.upper() in MISSING_TOKENS else cleaned_value
        idx += 1
    return idx, info


def parse_triplet(lines: List[str], idx: int) -> Tuple[int, List[str], List[str], List[str]]:
    """
    Parse a three-line CSV block: headers, units, and values.

    PISCAL format uses triplets for structured data (site info, parameters, measurements).
    Each triplet consists of:
    1. A header row with column names
    2. A units row describing units for each column
    3. A values row with actual data

    Args:
        lines: List of all lines from the CSV file.
        idx: Starting index to begin parsing from.

    Returns:
        Tuple of (next_line_index, headers_list, units_list, values_list).
        The index points to the line after the values row.
    """
    idx = next_nonempty(lines, idx)
    headers = parse_csv_line(lines[idx])
    idx += 1
    idx = next_nonempty(lines, idx)
    units = parse_csv_line(lines[idx])
    idx += 1
    idx = next_nonempty(lines, idx)
    values = parse_csv_line(lines[idx])
    idx += 1
    return idx, headers, units, values
