# piscal-processor

PISCAL CSV/Parquet processing: convert curves to Parquet, export to CSV/TSV, and use standard schemas. PISCAL is used at [LeafWeb.org](https://leafweb.org).

Install from PyPI, a local clone, or a Git URL (see below).

## Install

**From PyPI** (when published):

```bash
pip install piscal-processor
```

**Optional S3 support** (e.g. for `s3a://` paths):

```bash
pip install piscal-processor[s3]
```

**From a local clone** (development):

```bash
pip install -e /path/to/piscal-processor
```

**From a Git URL** (CI or private install): use a personal access token or SSH:

```bash
pip install "piscal-processor @ git+https://github.com/kolpacksoftware/piscal-processor.git@main"
# or
pip install "piscal-processor @ git+ssh://git@github.com/kolpacksoftware/piscal-processor.git@main"
```

You can pin a branch (`@main`), tag (`@v0.1.0`), or commit (`@abc1234`).

## CLI

**Convert** PISCAL CSV files to Parquet (metadata + measurements):

```bash
piscal-processor /path/to/csv_dir --output-dir parquet_output
```

Options: `--no-discover-pathway-subdirs`, `--source-pathway`, `--metadata-name`, `--measurements-name`. Input can be a local path or `s3a://` URI.

**Export** measurement Parquet to CSV or TSV:

```bash
piscal-processor-export curve_measurements.parquet -o out.tsv --format tsv --columns curve_id,AnetCO2,PARi
```

**Validate** that one or more CSV files are in PISCAL format:

```bash
piscal-processor-check-format tests/fixtures/sampleinput.csv
```

## Library

```python
from piscal_processor import (
    convert_curves,
    export_curves,
    get_backend,
    is_piscal_csv,
)

# Convert CSVs to DataFrames (or write Parquet via converter.normalize_and_write_parquet)
backend = get_backend("/path/to/csv_dir")
meta_df, meas_df = convert_curves("/path/to/csv_dir", backend, source_pathway="C3")

# Export measurements to CSV/TSV
export_curves(meas_df, "out.tsv", columns=["curve_id", "AnetCO2", "PARi"], format="tsv")

# Quickly validate that a single CSV file looks like a PISCAL/Leafweb curve file
ok = is_piscal_csv("/path/to/file.csv")
print(ok)
```

Schema constants and parser helpers are also available:

```python
from piscal_processor import STANDARD_MEASUREMENT_COLUMNS, STANDARD_METADATA_COLUMNS
from piscal_processor.parser import parse_csv_line, parse_key_value_section
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Documentation

- `docs/csv_structure.md`: CSV file structure (header, site/parameter blocks, measurement table).
- `docs/inputformat.txt`: PISCAL input file specification (official format description).
