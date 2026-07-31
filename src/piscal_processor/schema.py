"""
Standard column schemas for PISCAL Parquet outputs.

All batches are aligned to these column sets so outputs are consistent for
downstream use. Missing columns are filled with NA;
extra columns from source data are dropped (measurements) or folded into
the standard set via aliases (metadata).
"""

from typing import Dict

# ---------------------------------------------------------------------------
# Metadata table: one row per curve
# ---------------------------------------------------------------------------
STANDARD_METADATA_COLUMNS = [
    "curve_id",
    "pathway_subtype",
    "source_file",
    "Investigator name",
    "Contact information",
    "Site name in full",
    "Vegetation type",
    "Soil type",
    "Major species",
    "Sample leaf light environment",
    "Water stress assessment",
    "Instrument used",
    "Extra info",
    "SiteID",
    "SiteEnvironment",
    "Latitude",
    "Longitude",
    "Elevation",
    "SampleYear",
    "SampleDayOfYear",
    "GrowSeasonStart",
    "GrowSeasonEnd",
    "StandAge",
    "CanopyHeight",
    "LeafAreaIndex",
    "SpeciesSampled",
    "SampleHeight",
    "SampleLighting",
    "SampleCondition",
    "LeafAge",
    "SpecificLeafArea",
    "LfNitrogenContent",
    "LfCarbonContent",
    "LfPhosphorusContent",
    "WoodPorosity",
    "Sapwooddensity",
    "LeafLength",
    "LeafWidth",
    "LeafAbsorptance",
    "ChlabContent",
    "Carotenoid",
    "K",
    "Mg",
    "Ca",
    "Cu",
    "Zn",
    "Mn",
    "B",
    "Fe",
    "Mo",
    "Al",
    "Na",
    "S",
    "param_Gamma",
    "param_Kc25",
    "param_Ko25",
    "param_AlphaTPU",
    "param_Rd25",
    "param_ResistWP25",
    "param_ResistCH25",
    "measurement_units",
    "parameter_units",
]

# Metadata columns to coerce to float64 for consistent Parquet schema (Spark: INT32 vs double)
NUMERIC_METADATA_COLUMNS = [
    "Latitude",
    "Longitude",
    "Elevation",
    "SampleYear",
    "SampleDayOfYear",
    "GrowSeasonStart",
    "GrowSeasonEnd",
    "StandAge",
    "CanopyHeight",
    "LeafAreaIndex",
    "SampleHeight",
    "LeafAge",
    "SpecificLeafArea",
    "LfNitrogenContent",
    "LfCarbonContent",
    "LfPhosphorusContent",
    # WoodPorosity is deliberately absent: it is categorical ("ring porous",
    # "diffuse porous"), so coercing it to a number discards the value.
    "Sapwooddensity",
    "LeafLength",
    "LeafWidth",
    "LeafAbsorptance",
    "ChlabContent",
    "Carotenoid",
    "K",
    "Mg",
    "Ca",
    "Cu",
    "Zn",
    "Mn",
    "B",
    "Fe",
    "Mo",
    "Al",
    "Na",
    "S",
    "param_Gamma",
    "param_Kc25",
    "param_Ko25",
    "param_AlphaTPU",
    "param_Rd25",
    "param_ResistWP25",
    "param_ResistCH25",
]

# Every metadata column that is not numeric is emitted as a string, so each column
# has exactly one declared type regardless of what a given file happens to contain.
STRING_METADATA_COLUMNS = [
    col for col in STANDARD_METADATA_COLUMNS if col not in set(NUMERIC_METADATA_COLUMNS)
]

# Measurement columns to coerce to pandas StringDtype for consistent Parquet schema
MEASUREMENT_STRING_COLUMNS = [
    "curve_id",
    "SpeciesSampled",
    "Major_species",
    "Photosynthetic_pathway",
    "pathway_subtype",
    "DataType",
    "HHMMSS",
    "ObsDate",
]

# Map alternate CSV header names to standard metadata column names
METADATA_COLUMN_ALIASES: Dict[str, str] = {
    # Site / metadata header variants
    "Latitude(Degrees)": "Latitude",
    "Longitude(Degrees)": "Longitude",
    '"Extra info': "Extra info",
    '"Sample leaf light environment': "Sample leaf light environment",
    '"Water stress assessment': "Water stress assessment",
    # Legacy Leafweb / PISCAL names mapped to updated canonical names
    "LfPhosphContent": "LfPhosphorusContent",
    # Parameter triplet: legacy vs updated Leafweb names
    "param_Gamma*25": "param_Gamma",
    "param_KC25": "param_Kc25",
    "param_KO25": "param_Ko25",
    "param_Resistwpbs25": "param_ResistWP25",
    "param_Resistchm25": "param_ResistCH25",
}

# ---------------------------------------------------------------------------
# Measurement table: one row per observation
# ---------------------------------------------------------------------------
STANDARD_MEASUREMENT_COLUMNS = [
    "curve_id",
    "pathway_subtype",
    "SpeciesSampled",
    "Major_species",
    "Photosynthetic_pathway",
    "DataType",
    "ObsNo",
    "Year",
    "DayOfYear",
    "ObsDate",
    "HHMMSS",
    "AnetCO2",
    "AnetO2",
    "AnetVOC",
    "StomCond",
    "BLCond",
    "CO2i",
    "Trmmol",
    "VpdL",
    "LeafAreaMeasured",
    "StmRat",
    "Tair",
    "Tleaf",
    "TBlk",
    "CO2R",
    "CO2S",
    "H2OR",
    "H2OS",
    "RH_R",
    "RH_S",
    "MainFlowRate",
    "PARi",
    "PARo",
    "AirPress",
    "OxygenLevel",
    "TissueArea",
    "TissueMass",
    "PARi@Fs",
    "FoOrFsp",
    "FmOrFmp",
    "PAMFop",
    "FoDark",
    "FmDark",
    "NPQi",
    "NPQe",
    "qlake",
    "qpuddle",
    "PhiPSII",
    "condminineff",
    "VOCR",
    "VOCS_reading",
    "VOCs",
]

# Map alternate CSV measurement column names to standard
MEASUREMENT_COLUMN_ALIASES: Dict[str, str] = {
    # Required Leafweb input variables (legacy \"!\" headers and canonical forms)
    "!AnetCO2": "AnetCO2",
    "!StomCond": "StomCond",
    "!CO2i": "CO2i",
    "!Ci": "CO2i",
    "!Trmmol": "Trmmol",
    "!VpdL": "VpdL",
    "!Tleaf": "Tleaf",
    "!PARi": "PARi",
    "!AirPress": "AirPress",
    "AirPres": "AirPress",
    "Patm": "AirPress",
    "!FoorFs'": "FoOrFsp",
    "!FmorFm'": "FmOrFmp",
    # PAM fluorometry variants
    "PAMFo'": "PAMFop",
    # Gas exchange / VOC variants
    "AnetVoc": "AnetVOC",
    "OxygenLevel%": "OxygenLevel",
    "VOCS": "VOCS_reading",
    # Control / timing and instrument header variants
    "Obs": "ObsNo",
    "Flow": "MainFlowRate",
}

# Measurement columns carrying numbers. Emitted as float64 rather than letting pandas
# pick int64 or float64 per batch, which otherwise makes a column's type depend on
# which files were converted together (Spark: INT32 vs double).
NUMERIC_MEASUREMENT_COLUMNS = [
    col for col in STANDARD_MEASUREMENT_COLUMNS if col not in set(MEASUREMENT_STRING_COLUMNS)
]
