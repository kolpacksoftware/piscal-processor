"""Command-line interface for piscal-processor."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from piscal_processor.converter import (
    _pathway_subdirs_from_csv_paths,
    convert_curves,
    normalize_and_write_parquet,
    parse_curve_file_json,
)
from piscal_processor.export import export_curves
from piscal_processor.storage import get_backend
from piscal_processor.validation import validate_piscal_csv


def _parse_convert_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert PISCAL CSV curve files into metadata and measurement Parquet tables."
    )
    parser.add_argument(
        "input_dir",
        type=str,
        help="Directory containing the CSV files (one curve per file). Local path or s3a:// URI.",
    )
    parser.add_argument(
        "--no-discover-pathway-subdirs",
        action="store_true",
        help="Do not discover subdirs; treat input_dir as the folder of CSVs.",
    )
    parser.add_argument(
        "--source-pathway",
        type=str,
        default=None,
        help="Explicit pathway_subtype label (e.g. C4_NAD-ME). Only with --no-discover-pathway-subdirs.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="parquet_output",
        help="Destination directory for Parquet output.",
    )
    parser.add_argument(
        "--metadata-name",
        default="curve_metadata.parquet",
        help="Filename for the metadata parquet output.",
    )
    parser.add_argument(
        "--measurements-name",
        default="curve_measurements.parquet",
        help="Filename for the measurement parquet output.",
    )
    return parser.parse_args()


def _parse_export_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export measurement Parquet to CSV or TSV (optionally selected columns)."
    )
    parser.add_argument(
        "measurements_parquet",
        type=str,
        help="Path to curve_measurements.parquet (local or s3a://).",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        required=True,
        help="Output CSV or TSV path.",
    )
    parser.add_argument(
        "--columns",
        type=str,
        default=None,
        help="Comma-separated column names to export (default: all).",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=("csv", "tsv"),
        default="csv",
        help="Output format: csv or tsv.",
    )
    return parser.parse_args()


def _parse_check_format_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check whether one or more CSV files are in PISCAL/Leafweb format."
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="One or more CSV files to validate.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Enable strict validation (reserved for future tightening of rules).",
    )
    return parser.parse_args()


def main() -> None:
    """Main entry: convert CSV files to Parquet (default subcommand)."""
    args = _parse_convert_args()
    output_dir = Path(args.output_dir)

    if args.no_discover_pathway_subdirs:
        read_backend = get_backend(args.input_dir)
        metadata_df, measurement_df = convert_curves(
            args.input_dir, read_backend, source_pathway=args.source_pathway
        )
        normalize_and_write_parquet(
            metadata_df,
            measurement_df,
            output_dir,
            metadata_name=args.metadata_name,
            measurements_name=args.measurements_name,
        )
        print(f"Wrote metadata to {output_dir / args.metadata_name}")
        print(f"Wrote measurements to {output_dir / args.measurements_name}")
        return

    read_backend = get_backend(args.input_dir)
    csv_paths = read_backend.list_csv_paths(args.input_dir)
    subdirs = _pathway_subdirs_from_csv_paths(args.input_dir, csv_paths)
    parent = args.input_dir.rstrip("/").split("/")[-1]

    if not subdirs:
        metadata_df, measurement_df = convert_curves(
            args.input_dir, read_backend, source_pathway=None
        )
        normalize_and_write_parquet(
            metadata_df,
            measurement_df,
            output_dir,
            metadata_name=args.metadata_name,
            measurements_name=args.measurements_name,
        )
        print(f"Wrote metadata to {output_dir / args.metadata_name}")
        print(f"Wrote measurements to {output_dir / args.measurements_name}")
    else:
        for sub in subdirs:
            input_path = f"{args.input_dir.rstrip('/')}/{sub}"
            source_pathway = f"{parent}_{sub}"
            sub_output = output_dir / source_pathway
            metadata_df, measurement_df = convert_curves(
                input_path, read_backend, source_pathway=source_pathway
            )
            normalize_and_write_parquet(
                metadata_df,
                measurement_df,
                sub_output,
                metadata_name=args.metadata_name,
                measurements_name=args.measurements_name,
            )
            print(f"Wrote {source_pathway} to {sub_output}")


def export_main() -> None:
    """CLI entry for export: Parquet -> CSV/TSV."""
    args = _parse_export_args()
    backend = get_backend(args.measurements_parquet)
    measurement_df = backend.read_parquet(args.measurements_parquet)
    columns = [c.strip() for c in args.columns.split(",")] if args.columns else None
    export_curves(
        measurement_df,
        args.output,
        columns=columns,
        format=args.format,
    )
    print(f"Exported to {args.output}")


def check_format_main() -> None:
    """CLI entry for format validation of PISCAL CSV files."""
    args = _parse_check_format_args()
    any_failed = False

    for path in args.files:
        ok, errors = validate_piscal_csv(path, strict=args.strict)
        if ok:
            print(f"{path}: OK")
        else:
            any_failed = True
            reason = "; ".join(errors) if errors else "Unknown validation error"
            print(f"{path}: NOT PISCAL - {reason}")

    sys.exit(1 if any_failed else 0)


def _parse_parse_file_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Parse one PISCAL/Leafweb CSV into JSON "
            "(metadata object + measurements array) on stdout."
        )
    )
    parser.add_argument(
        "file",
        type=str,
        help="Path to a single PISCAL CSV file (local path or s3a:// URI).",
    )
    parser.add_argument(
        "--source-pathway",
        type=str,
        default=None,
        help="Optional pathway_subtype label (e.g. C3_photosynthesis_leafweb).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Write JSON to this path instead of stdout.",
    )
    return parser.parse_args()


def parse_file_main() -> None:
    """CLI entry: parse one CSV file and emit JSON metadata + measurements."""
    args = _parse_parse_file_args()
    try:
        backend = get_backend(args.file)
        result = parse_curve_file_json(
            args.file, backend, source_pathway=args.source_pathway
        )
    except Exception as exc:  # noqa: BLE001 - surface any parse failure to the caller
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, allow_nan=False)
            f.write("\n")
    else:
        json.dump(result, sys.stdout, allow_nan=False)
        sys.stdout.write("\n")
