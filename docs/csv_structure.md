# CSV Structure Summary

Each `20251112AI_Bauhinia_glauca*.csv` file follows the PISCAL input spec:

1. **Descriptive header (lines 1–11)**
   - Free-form `Label: value` pairs describing pathway, investigator, site, vegetation, stress notes, and instrument.
   - Our parser stores every label verbatim so new metadata fields automatically propagate.
2. **Site block (lines 12–14)**
   - Line 12: comma-separated column names such as `SiteID`, `Latitude`, `SampleYear`, `SpeciesSampled`.
   - Line 13: Units row (deg, m, %, etc.).
   - Line 14: Values for the curve; `-9999` marks missing.
3. **Parameter block (lines 15–17)**
   - Line 15: Parameter labels (Gamma, Kc25, Ko25, AlphaTPU, Rd25, ResistWP25, ResistCH25).
   - Line 16: Units row (Pa, µmol m⁻² s⁻¹, etc.).
   - Line 17: Numeric overrides; `-9999` means let the solver fit them.
4. **Measurement table (line 18 onward)**
   - Line 18: Column names from Licor output (DataType, Year, DayOfYear, HHMMSS, AnetCO2, ..., VOCs).
   - Line 19: Units (µmol m⁻² s⁻¹, ppm, kPa, °C, etc.).
   - Lines 20+: Observations sorted by `HHMMSS`. Required columns prefixed with `!` in the spec are present in the data (`StomCond`, `CO2i`, `Trmmol`, `VpdL`, `Tleaf`, `PARi`).

**Delimiters & Sentinels**
- Strict CSV with commas; some values have leading periods (e.g., `.0430800830`), handled by the standard CSV parser.
- Missing values consistently expressed as `-9999` (with optional decimals) or `NA`.

**Additional notes**
- Each file contains exactly one curve, so we key by filename.
- The observation block mixes integer and float columns; we coerce numeric columns opportunistically based on actual data.
