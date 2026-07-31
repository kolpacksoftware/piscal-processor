# Legacy Fortran input format

The PISCAL Fortran binary (`ToLeafGasOptimization.f`) does **not** read
measurement columns by name. After a width-based format sniffer finds the
site / parameter / data blocks, every data field is taken from a fixed
position (`charvars(5)` = AdjPhoto, `charvars(6)` = StomCond,
`charvars(23)` = PARi, and so on).

LeafWeb-standard CSVs (StandardDataForAI and current Leafweb exports) use a
different column order and a wider site block. Feeding them to the binary
unchanged either fails format detection or silently maps the wrong values
into the fitter.

`piscal_processor.legacy` rewrites a parsed curve into the Licor layout the
binary expects:

| Block | Columns | Notes |
|-------|---------|-------|
| Descriptive | 10 free-text `Key: value` lines | Quoted when the value contains a comma |
| Site | 21 | No `SiteEnvironment`; includes `AveTimeResolution` |
| Parameters | 7 | `Gamma*,Kc,Ko,Alpha,Rd,ResistWP25,ResistCH25` |
| Measurements | 38 | Starts with `Obs`, includes `!AdjPhoto` |

## What guarantees correctness

Because the reads are positional, the property that matters is column *order*,
not column count. Positions 1–19 (site), 1–6 (parameters), and 1–31
(measurements) are emitted in exactly the order given by `docs/inputformat.txt`,
which is also the layout of `tests/fixtures/sampleinput.csv`. That alignment is
pinned by `test_emitted_columns_match_spec_positions`, so a reordering breaks the
build rather than silently feeding the fitter the wrong variable.

Position 6 of the parameter block is the one intentional naming difference: the
spec calls it `gi` (internal conductance, `umol/m2/s/Pa`) and the standard schema
calls it `ResistWP25`. Same quantity, same slot.

## Sniffer constraints (unverified assumption)

Everything past those positions is an append-only extension: site 20–21, the 7th
parameter, and measurement columns 32–38. Emitting them assumes the detector in
`ToLeafGasOptimization.f` accepts a range of block widths rather than exact
counts:

- Site header / units / values: identical counts, 15–25 → emit **21**
- Parameter header / units / values: identical counts, 5–10 → emit **7**
- Data header, units, and the first **four** data rows: identical counts ≥ 25 → emit **38**, and refuse conversion when there are fewer than 4 data rows

> **This range is not verified in this repo.** `ToLeafGasOptimization.f` is not
> vendored here, and the only legacy reference available (`sampleinput.csv`) is
> 19 / 6 / 31, so it does not exercise the wider blocks. If the sniffer turns out
> to require exact widths, trim `LEGACY_SITE_COLUMNS`, `LEGACY_PARAM_COLUMNS`,
> and `LEGACY_MEASUREMENT_COLUMNS` (plus their unit rows) back to 19 / 6 / 31.
> The positional test above keeps that trim safe.

Note that an already-legacy source is copied through unchanged, so the tool emits
19 / 6 / 31 for pass-through and 21 / 7 / 38 for conversions.

## Columns left as `-9999`

Every column is populated when the source has a value for it, including the
Licor-only columns (`FTime`, `CsMch`, `HsMch`, `StableF`, `Status`) that exist in
legacy files but not in the standard schema. These end up `-9999` only when the
source genuinely lacks them:

- `Fs` and `MeasLight`: no standard-schema equivalent
- `OxygenPress`: passed through when present, never derived (see below)
- `DataType`, `PhiPS2`: absent from older Licor exports

`Photo` (position 4) is the raw rate and `!AdjPhoto` (5) the leakage-corrected
one. When the source has both, both are preserved. Standard files carry only the
corrected rate, so `Photo` falls back to it rather than being left empty.

`TissueArea` / `TissueMass` are passed through only when both are positive
**and** `CO2R`, `H2OR`, and `MainFlowRate` are present (the mass-based
recompute path needs them). Otherwise both are `-9999`.

`LegacyConversionReport.notes` lists, per conversion, which columns came out
`-9999` for every row and which source columns and metadata fields had no legacy
slot, so nothing is dropped without being reported.

### The OxygenPress unit conflict

`OxygenPress` is deliberately never computed from `OxygenLevel%`, even though
`OxygenLevel%` × `Press` would give a partial pressure, because the target unit
is ambiguous:

| Source | Declared unit |
|--------|---------------|
| `docs/inputformat.txt` line 86 | `Pa` |
| `sampleinput.csv` units row and this emitter | `KPA` |

That is a 1000x discrepancy. Resolve it against the Fortran source before
populating the column; guessing would put a plausible-looking but wrong O₂
partial pressure into the fitter, which is worse than `-9999`.

## Fields with no legacy slot

The legacy layout is narrower than the standard schema, so conversion drops:

- Measurements: `ObsDate`, `AnetO2`, `AnetVOC`, `OxygenLevel`, `PARi@Fs`,
  `FoDark`, `FmDark`, `PamFo'`, `VOCR`, `VOCS_reading`
- Site: `SiteEnvironment`, `SampleLighting`, `SampleCondition`, `LeafLength`,
  `LeafWidth`, and the trace-element columns

`Photosynthetic pathway` is the exception. The legacy layout has exactly 10
descriptive lines and no slot for it, but C3 vs C4 changes how a curve should be
fitted, so it is appended to the `Extra info` line instead of being dropped.

## Usage

```bash
piscal-processor-to-legacy standard.csv -o legacy.csv

# Rewrite even when the source is already legacy, instead of copying it through.
# Round-trips every column the legacy layout has a slot for; the report lists
# anything dropped.
piscal-processor-to-legacy already_legacy.csv -o rebuilt.csv --force
```

```python
from piscal_processor import (
    LegacyConversionError,
    needs_legacy_conversion,
    write_legacy_input,
)

if needs_legacy_conversion("standard.csv"):
    report = write_legacy_input("standard.csv", "legacy.csv")
    for note in report.notes:
        print(note)
```

`write_legacy_input` and `needs_legacy_conversion` raise `LegacyConversionError`
for input that is not a PISCAL CSV or that has fewer than 4 data rows. Nothing is
written when conversion fails, so a failed run never leaves a partial file that
looks convertible.
