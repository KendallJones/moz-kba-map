#!/usr/bin/env python3
"""
convert_shapefile.py
====================
Converts your Mozambique KBA shapefile to the GeoJSON format
required by the web map.

USAGE
-----
1. Install dependencies (once):
       pip install geopandas shapely

2. Run the script:
       python convert_shapefile.py

   Or with explicit paths:
       python convert_shapefile.py --input path/to/your.shp --output kba-data.js

WHAT IT DOES
------------
- Reads your .shp file (plus associated .dbf, .prj, .shx files)
- Reprojects to WGS84 (lat/lon) if needed
- Writes kba-data.js with a var KBA_GEOJSON = {...} assignment
  so the web map can load it as a plain <script> tag
- Prints a summary of fields found in your shapefile so you can
  map them to the properties the web map expects (see FIELD_MAP below)
"""

import json
import argparse
import sys
from pathlib import Path

try:
    import geopandas as gpd
except ImportError:
    sys.exit("❌  geopandas not found. Run:  pip install geopandas")


# ── FIELD MAP ──────────────────────────────────────────────────────────────
# Map your shapefile's column names → web map property names.
# Edit the LEFT side to match the actual column names in your .shp file.
# Run the script once with --list-fields to see what columns you have.
#
# Set a value to None to skip that field.

FIELD_MAP = {
    # Shapefile column       # Web map property
    "KBA_Name":              "name",
    "ID":                    "site_id",
    "Region":                "broad_region",
    "KBA_Area":              "area_ha",
    "Trigger_BD":            "trigger_groups",
    "Threats":               "threats_raw",      # new shapefile uses "Threats"
    "KBA_Criter":            "kba_criteria",     # new shapefile uses "KBA_Criter"
    # Columns we don't need — set to None to skip
    "Country":               None,
    "Created_By":            None,
    "Del_text":              None,
    "layer":                 None,
    "path":                  None,
}

# ── DEFAULTS ───────────────────────────────────────────────────────────────
DEFAULT_INPUT  = "kba_mozambique.shp"   # change if your file has a different name
DEFAULT_OUTPUT = "kba-data.js"


def convert(input_path: str, output_path: str, list_fields: bool = False):
    print(f"📂  Reading: {input_path}")
    gdf = gpd.read_file(input_path)

    # Print available fields
    print(f"\n📋  Fields found in shapefile ({len(gdf.columns)} columns):")
    for col in gdf.columns:
        if col != "geometry":
            sample = gdf[col].iloc[0] if len(gdf) > 0 else "—"
            print(f"      {col:<30} (e.g. {sample!r})")

    if list_fields:
        return

    # Reproject to WGS84 if needed
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        print(f"\n🔄  Reprojecting from {gdf.crs} → WGS84 …")
        gdf = gdf.to_crs(epsg=4326)

    feature_count = len(gdf)
    print(f"\n✅  {feature_count} features found. Converting …")

    features = []
    for _, row in gdf.iterrows():
        # Build properties using FIELD_MAP
        props = {}
        for shp_col, map_key in FIELD_MAP.items():
            if map_key is None:
                continue
            val = row.get(shp_col)
            if val is not None:
                # Convert numpy types to plain Python
                try:
                    val = val.item()
                except AttributeError:
                    pass
                props[map_key] = val

        # Split the threats string into a proper list
        import re
        threats_raw = props.pop("threats_raw", "") or ""
        parts = re.split(r'[;]|(?=\b(?:i{1,3}v?|iv|v?i{0,3})\))', threats_raw)
        threats_list = [p.strip().lstrip("ivxlIVXL)., ") for p in parts if p.strip()]
        props["threats"] = [t for t in threats_list if len(t) > 3]

        # Auto-build KBA rationale from shapefile fields
        criteria = props.get("kba_criteria", "") or ""
        classif  = props.get("classification", "") or ""
        area     = props.get("area_ha")
        trig     = props.get("trigger_groups", "") or ""
        rationale_parts = []
        if criteria:
            rationale_parts.append(f"Meets KBA criteria: {criteria}.")
        if classif and classif != "N/A":
            rationale_parts.append(f"Designated as: {classif}.")
        if trig:
            rationale_parts.append(f"Trigger biodiversity groups: {trig}.")
        if area:
            rationale_parts.append(f"Total area: {float(area):,.0f} ha.")
        props["kba_rationale"] = " ".join(rationale_parts)

        # Scaffold remaining fields (populated later by extract/populate scripts)
        props.setdefault("coordinates", "")
        props.setdefault("protection_category", "")
        props.setdefault("protection_category_pt", "")
        props.setdefault("preexisting_designation", "")
        props.setdefault("preexisting_designation_pt", "")
        props.setdefault("description", "")
        props.setdefault("description_pt", "")
        props.setdefault("kba_rationale_pt", "")
        props.setdefault("trigger_species", [])
        props.setdefault("trigger_species_pt", [])
        props.setdefault("threats_pt", [])
        props.setdefault("satellite_image", "")
        props.setdefault("photos", [])

        geom = row.geometry.__geo_interface__
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": props,
        })

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    # Wrap in a JS variable assignment
    js_content = (
        "// Auto-generated by convert_shapefile.py — do not edit geometry by hand.\n"
        "// Populate description, kba_rationale, threats, trigger_species and photos for each feature.\n\n"
        "var KBA_GEOJSON = "
        + json.dumps(geojson, ensure_ascii=False, indent=2)
        + ";\n"
    )

    out = Path(output_path)
    out.write_text(js_content, encoding="utf-8")
    print(f"\n🎉  Done! Wrote {feature_count} features to: {out.resolve()}")
    print("\nNext steps:")
    print("  1. Copy the generated kba-data.js into your web map folder.")
    print("  2. Open kba-data.js and fill in description, kba_rationale,")
    print("     threats, trigger_species and photos for each site.")
    print("  3. Open index.html in a browser (via a local server — see README).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert KBA shapefile to web map GeoJSON")
    parser.add_argument("--input",       default=DEFAULT_INPUT,  help="Path to .shp file")
    parser.add_argument("--output",      default=DEFAULT_OUTPUT, help="Output .js file path")
    parser.add_argument("--list-fields", action="store_true",    help="Just print fields, don't convert")
    args = parser.parse_args()

    convert(args.input, args.output, args.list_fields)