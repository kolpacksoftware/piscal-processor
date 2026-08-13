# Changelog

All notable changes to this project are documented here. This project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 0.2.1

### Changed

- `validate_piscal_csv` accepts GFS-3000 / Cornell parameter headers
  (`Gamma*_25oC`, `Kc_25oC`, `Ko_25oC`, `Alpha_25oC`, `Rd_25oC`, `rwp_25oC`,
  `rch_25oC`) alongside the existing legacy and Leafweb names. Classic `Gamma*`
  files still match via `Kc`/`Ko`/`Alpha`/`Rd`/`gi`.
- `validate_piscal_csv` reads files with the same utf-8 then iso-8859-1 fallback
  as `FilesystemBackend.read_text`, so latin-1 LeafWeb.org CSVs no longer raise
  `UnicodeDecodeError` before parse.
- `parse_curve_file` applies `METADATA_COLUMN_ALIASES` the same way
  `parse_curve_file_json` does (canonical wins if both keys are present), so
  `Latitude(Degrees)` and `param_Gamma*` land on `Latitude` and `param_Gamma`.
- GFS/Cornell param names alias onto the canonical `param_*` keys.
- `ChamberArea` aliases onto `LeafAreaMeasured`.
- After measurement aliasing and numeric coerce, missing `AnetCO2` is filled
  from `Photo` without overwriting real AdjPhoto-derived values. `Photo` stays
  its own column. The legacy emitter still writes Photo and `!AdjPhoto` as
  distinct fields.

## 0.2.0

### Added

- `piscal-processor-to-legacy` CLI and `write_legacy_input` / `to_legacy_text` /
  `needs_legacy_conversion` library functions, which rewrite a PISCAL/Leafweb CSV
  into the positional Licor layout the Fortran binary reads. See
  `docs/legacy_format.md`, including the documented assumption about the format
  sniffer's accepted block widths.
- `docs/legacy_format.md` describing the legacy layout, the columns that have no
  legacy slot, and the unresolved `OxygenPress` Pa vs kPa conflict between
  `docs/inputformat.txt` and `tests/fixtures/sampleinput.csv`.

### Changed

- **Measurement column aliases now resolve additional legacy header spellings**,
  which changes the Parquet and JSON output for files that use them. `AdjPhoto`
  and `!AdjPhoto` now populate `AnetCO2`, `Press` populates `AirPress`, `Area`
  populates `LeafAreaMeasured`, and `PhiPS2` populates `PhiPSII`. Previously
  these columns were dropped when reindexing onto the standard schema, so curves
  such as `sampleinput.csv` gained values in columns that used to be null.
  Downstream consumers that relied on those columns being empty should be
  re-checked.
- Metadata parameter aliases now cover the shorter legacy spellings
  (`param_Gamma*`, `param_Kc`, `param_Ko`, `param_Alpha`, `param_Rd`, `param_gi`),
  so parameter triplets written with spec names land under the canonical keys.
- `FilesystemBackend.write_text` and `S3Backend.write_text` pin UTF-8 instead of
  relying on the machine's locale encoding.
- Top-level imports are now lazy, resolved through a module `__getattr__`. The
  public names in `piscal_processor.__all__` are unchanged, but `import
  piscal_processor` no longer pulls in pandas and pyarrow up front, so the legacy
  conversion path stays lightweight. Code that relied on the side effect of
  submodules being imported eagerly should import them explicitly.
