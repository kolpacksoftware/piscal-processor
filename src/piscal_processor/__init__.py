"""
piscal-processor: PISCAL CSV/Parquet processing: convert curves, export to CSV/TSV, and use standard schemas.

Use as a library:
  from piscal_processor import convert_curves, export_curves, get_backend
  meta, meas = convert_curves(input_dir, get_backend(input_dir))
  export_curves(meas, "out.tsv", columns=["curve_id", "AnetCO2"], format="tsv")

CLI: piscal-processor (convert), piscal-processor-export (export to CSV/TSV),
piscal-processor-check-format (validate CSV format),
piscal-processor-parse-file (parse one CSV to JSON),
piscal-processor-to-legacy (rewrite to Fortran Licor layout).

Heavy imports (pandas/pyarrow via converter) are lazy so
``from piscal_processor.legacy import write_legacy_input`` stays lightweight.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "convert_curves",
    "parse_curve_file",
    "parse_curve_file_json",
    "export_curves",
    "extract_columns",
    "get_backend",
    "StorageBackend",
    "FilesystemBackend",
    "S3Backend",
    "next_nonempty",
    "normalize_scalar",
    "parse_csv_line",
    "parse_key_value_section",
    "parse_triplet",
    "STANDARD_MEASUREMENT_COLUMNS",
    "STANDARD_METADATA_COLUMNS",
    "MEASUREMENT_COLUMN_ALIASES",
    "METADATA_COLUMN_ALIASES",
    "MEASUREMENT_STRING_COLUMNS",
    "NUMERIC_MEASUREMENT_COLUMNS",
    "NUMERIC_METADATA_COLUMNS",
    "STRING_METADATA_COLUMNS",
    "is_piscal_csv",
    "validate_piscal_csv",
    "LEGACY_MEASUREMENT_COLUMNS",
    "LEGACY_PARAM_COLUMNS",
    "LEGACY_SITE_COLUMNS",
    "LegacyConversionError",
    "LegacyConversionReport",
    "needs_legacy_conversion",
    "to_legacy_text",
    "write_legacy_input",
]

_LAZY_EXPORTS = {
    "convert_curves": ("piscal_processor.converter", "convert_curves"),
    "parse_curve_file": ("piscal_processor.converter", "parse_curve_file"),
    "parse_curve_file_json": ("piscal_processor.converter", "parse_curve_file_json"),
    "export_curves": ("piscal_processor.export", "export_curves"),
    "extract_columns": ("piscal_processor.export", "extract_columns"),
    "get_backend": ("piscal_processor.storage", "get_backend"),
    "StorageBackend": ("piscal_processor.storage", "StorageBackend"),
    "FilesystemBackend": ("piscal_processor.storage", "FilesystemBackend"),
    "S3Backend": ("piscal_processor.storage", "S3Backend"),
    "next_nonempty": ("piscal_processor.parser", "next_nonempty"),
    "normalize_scalar": ("piscal_processor.parser", "normalize_scalar"),
    "parse_csv_line": ("piscal_processor.parser", "parse_csv_line"),
    "parse_key_value_section": ("piscal_processor.parser", "parse_key_value_section"),
    "parse_triplet": ("piscal_processor.parser", "parse_triplet"),
    "STANDARD_MEASUREMENT_COLUMNS": ("piscal_processor.schema", "STANDARD_MEASUREMENT_COLUMNS"),
    "STANDARD_METADATA_COLUMNS": ("piscal_processor.schema", "STANDARD_METADATA_COLUMNS"),
    "MEASUREMENT_COLUMN_ALIASES": ("piscal_processor.schema", "MEASUREMENT_COLUMN_ALIASES"),
    "METADATA_COLUMN_ALIASES": ("piscal_processor.schema", "METADATA_COLUMN_ALIASES"),
    "MEASUREMENT_STRING_COLUMNS": ("piscal_processor.schema", "MEASUREMENT_STRING_COLUMNS"),
    "NUMERIC_MEASUREMENT_COLUMNS": ("piscal_processor.schema", "NUMERIC_MEASUREMENT_COLUMNS"),
    "NUMERIC_METADATA_COLUMNS": ("piscal_processor.schema", "NUMERIC_METADATA_COLUMNS"),
    "STRING_METADATA_COLUMNS": ("piscal_processor.schema", "STRING_METADATA_COLUMNS"),
    "is_piscal_csv": ("piscal_processor.validation", "is_piscal_csv"),
    "validate_piscal_csv": ("piscal_processor.validation", "validate_piscal_csv"),
    "LEGACY_MEASUREMENT_COLUMNS": ("piscal_processor.legacy", "LEGACY_MEASUREMENT_COLUMNS"),
    "LEGACY_PARAM_COLUMNS": ("piscal_processor.legacy", "LEGACY_PARAM_COLUMNS"),
    "LEGACY_SITE_COLUMNS": ("piscal_processor.legacy", "LEGACY_SITE_COLUMNS"),
    "LegacyConversionError": ("piscal_processor.legacy", "LegacyConversionError"),
    "LegacyConversionReport": ("piscal_processor.legacy", "LegacyConversionReport"),
    "needs_legacy_conversion": ("piscal_processor.legacy", "needs_legacy_conversion"),
    "to_legacy_text": ("piscal_processor.legacy", "to_legacy_text"),
    "write_legacy_input": ("piscal_processor.legacy", "write_legacy_input"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attr = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    from importlib import import_module

    value = getattr(import_module(module_name), attr)
    globals()[name] = value
    return value
