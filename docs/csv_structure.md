# CSV Structure Summary

1. **Descriptive header (lines 1–11)**
   - Free-form `Label: value` pairs describing pathway, investigator, site, vegetation, stress notes, and instrument.
   - Our parser stores every label verbatim so new metadata fields automatically propagate.
2. **Site block (lines 12–14)**
   - Line 12: comma-separated column names such as `SiteID`, `SiteEnvironment`, `Latitude(Degrees)`, `Longitude(Degrees)`, `Elevation`, `SampleYear`, `SampleDayOfYear`, `GrowSeasonStart`, `GrowSeasonEnd`, `StandAge`, `CanopyHeight`, `LeafAreaIndex`, `SpeciesSampled`, `SampleHeight`, `SampleLighting`, `SampleCondition`, `LeafAge`, `SpecificLeafArea`, `LfNitrogenContent`, `LfCarbonContent`, `LfPhosphorusContent`, `WoodPorosity`, `Sapwooddensity`, `LeafLength`, `LeafWidth`.
   - Line 13: Units row (deg, m, %, cm, cm² g⁻¹, etc.).
   - Line 14: Values for the curve; missing values must be filled with `-9999` (or `NA` for non-numeric identifiers).
   - Both legacy and Leafweb-standard header names are accepted on ingest; for example, `Latitude(Degrees)` and legacy `Latitude` both map to the same internal `Latitude` column, and `LfPhosphContent` is normalized to `LfPhosphorusContent`.
3. **Parameter block (lines 15–17)**
   - Line 15: Parameter labels following the Leafweb standard: `Gamma*25`, `KC25`, `KO25`, `AlphaTPU`, `Rd25`, `Resistwpbs25`, `Resistchm25`.
   - Line 16: Units row (Pa, µmol m⁻² s⁻¹, µmol⁻¹ m² s Pa, etc.).
   - Line 17: Numeric overrides at 25 °C; `-9999` means “use Leafweb defaults / fit from data”.
   - Legacy parameter names from PISCAL (`Gamma`, `Kc25`, `Ko25`, and scalar `gi`) are still accepted; on ingest they are mapped into the new resistance parameters, and the single `gi` field is not retained as a separate column in the normalized schema.
4. **Measurement table (line 18 onward)**
   - Line 18: Column names for control/timing, gas exchange, PAM fluorometry, and VOC data. Typical headers include `DataType`, `ObsNo` (legacy `Obs`), `ObsDate`, `HHMMSS`, `!AnetCO2`, `AnetO2`, `AnetVOC`, `!StomCond`, `!CO2i` (legacy `!Ci`), `!Trmmol`, `!VpdL`, `LeafAreaMeasured`, `StmRat`, `BLCond`, `Tair`, `!Tleaf`, `TBlk`, `CO2R`, `CO2S`, `H2OR`, `H2OS`, `RH_R`, `RH_S`, `MainFlowRate` (legacy `Flow`), `!PARi`, `PARo`, `!AirPress`, `OxygenLevel%`, `TissueArea`, `TissueMass`, `PARi@Fs`, `!FoorFs'`, `!FmorFm'`, `FoDark`, `FmDark`, `PamFo'`, `VOCR`, `VOCS`.
   - Line 19: Units row (µmol m⁻² s⁻¹, µmol mol⁻¹, kPa, °C, %, ppb, etc.).
   - Lines 20+: Observations sorted by `HHMMSS`. Variables starting with `!` in the Leafweb specification are required for Leafweb analyses; this library accepts files with missing or `-9999` values for these columns but will emit warnings when they are absent or entirely empty.

**Delimiters & Sentinels**
- Strict CSV with commas; some values have leading periods (e.g., `.0430800830`), handled by the standard CSV parser.
- Missing values consistently expressed as `-9999` (with optional decimals) or `NA`.

**Additional notes**
- Each file contains exactly one curve, so we key by filename.
- The observation block mixes integer and float columns; we coerce numeric columns opportunistically based on actual data, while keeping categorical fields such as `SiteEnvironment`, `SampleLighting`, and `SampleCondition` as strings.
- Instrument-specific legacy fields that have no Leafweb equivalent (e.g. `AveTimeResolution`, `gi`, `FTime`, `CsMch`, `HsMch`, `StableF`, `Status`) are ignored on ingest and not included in the standard Parquet schema.

The `piscal-processor` library includes a lightweight validator (`is_piscal_csv` /
`validate_piscal_csv`) that uses this structure as its reference when deciding if a
CSV file appears to be in PISCAL/Leafweb format. Both legacy PISCAL headers and
Leafweb-standard headers are accepted.
