"""
piscal-processor: PISCAL CSV/Parquet processing: convert curves, export to CSV/TSV, and use standard schemas.

Use as a library:
  from piscal_processor import convert_curves, export_curves, get_backend
  meta, meas = convert_curves(input_dir, get_backend(input_dir))
  export_curves(meas, "out.tsv", columns=["curve_id", "AnetCO2"], format="tsv")

CLI: piscal-processor (convert), piscal-processor-export (export to CSV/TSV).
"""

from piscal_processor.converter import convert_curves, parse_curve_file
from piscal_processor.export import export_curves, extract_columns
from piscal_processor.parser import (
    next_nonempty,
    normalize_scalar,
    parse_csv_line,
    parse_key_value_section,
    parse_triplet,
)
from piscal_processor.schema import (
    MEASUREMENT_COLUMN_ALIASES,
    MEASUREMENT_STRING_COLUMNS,
    METADATA_COLUMN_ALIASES,
    NUMERIC_METADATA_COLUMNS,
    STANDARD_MEASUREMENT_COLUMNS,
    STANDARD_METADATA_COLUMNS,
)
from piscal_processor.storage import FilesystemBackend, S3Backend, StorageBackend, get_backend

__all__ = [
    "convert_curves",
    "parse_curve_file",
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
    "NUMERIC_METADATA_COLUMNS",
]
