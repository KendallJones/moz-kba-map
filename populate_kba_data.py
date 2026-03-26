#!/usr/bin/env python3
"""
populate_kba_data.py
====================
Merges factsheet content + photo/satellite paths into kba-data.js.

Run AFTER:
  1. convert_shapefile.py  (generates kba-data.js from shapefile)
  2. extract_factsheets.py (generates factsheet_data.json from PDFs)
  3. Media assets copied to photos/ and satellite/ folders

USAGE:
    python3 populate_kba_data.py
"""

import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

BASE = Path(__file__).parent
KBA_JS   = BASE / "kba-data.js"
FS_JSON  = BASE / "factsheet_data.json"
PHOTOS_DIR    = BASE / "photos"
SATELLITE_DIR = BASE / "satellite"
OUTPUT   = KBA_JS  # overwrite in place


# ── Manual overrides (shapefile name → factsheet EN name) ──────────────────
# Add entries here when automated matching fails.
MANUAL_MATCHES = {
    "Gorongosa and Marromeu Complex":       "Gorongosa-Marromeu",
    "Great Bazaruto":                       "Grande Bazaruto",
    "Tchuma-Tchato_Cahora Bassa Lake":      "Tchuma Tchato",
    "Mount_Mabu":                           "Mount Mabu",
    "Mount_Chiperoni":                      "Mount Chiperone",
    "Mount_Inago":                          "Mount Inago",
    "Mount_Namuli":                         "Mount Namuli",
    "Manhiça-Bilene (Limpopo floodlain)":   "Manhiça-Bilene",
    "Ponta do Ouro Marine Partial Reserve": "Ponta do Ouro",
    "Chimanimani National Park":             "Chimanimani",
    "Nkwichi Bay":                          None,   # not in PDF — skip
}


# ── Fuzzy name matching ─────────────────────────────────────────────────────

def normalise(s):
    """Lowercase, strip accents, remove non-alphanumeric."""
    s = s.lower()
    replacements = {
        'á':'a','à':'a','â':'a','ã':'a','ä':'a',
        'é':'e','è':'e','ê':'e','ë':'e',
        'í':'i','ì':'i','î':'i','ï':'i',
        'ó':'o','ò':'o','ô':'o','õ':'o','ö':'o',
        'ú':'u','ù':'u','û':'u','ü':'u',
        'ç':'c','ñ':'n','ý':'y',
    }
    for accented, plain in replacements.items():
        s = s.replace(accented, plain)
    return re.sub(r'[^a-z0-9]', '', s)


def best_match(shp_name, factsheet_keys):
    """Find the factsheet key that best matches the shapefile feature name."""
    # Check manual overrides first
    if shp_name in MANUAL_MATCHES:
        return MANUAL_MATCHES[shp_name]  # may be None (intentional skip)

    norm_shp = normalise(shp_name)

    best = None
    best_score = 0.0
    for key in factsheet_keys:
        norm_key = normalise(key)
        score = SequenceMatcher(None, norm_shp, norm_key).ratio()
        if score > best_score:
            best_score = score
            best = key

    # Only accept matches above a high threshold
    return best if best_score >= 0.65 else None


# ── Photo discovery ─────────────────────────────────────────────────────────

IMG_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.heic', '.heif'}

def find_photos_for_site(site_id):
    """
    Find all photos for a site given its sequential shapefile ID (1-30).
    Photos are in folders named like '10-Mount_Inago/'.
    Returns list of relative paths (relative to webmap root).
    """
    if not PHOTOS_DIR.exists():
        return []

    # Find folder whose name starts with the site_id number
    prefix = str(int(site_id))
    matching_dirs = [
        d for d in PHOTOS_DIR.iterdir()
        if d.is_dir() and re.match(rf'^0*{re.escape(prefix)}[-_]', d.name)
    ]

    photos = []
    for folder in matching_dirs:
        for img in sorted(folder.rglob('*')):
            if img.is_file() and img.suffix.lower() in IMG_EXTS:
                # Skip macOS hidden files
                if img.name.startswith('.') or '.__' in img.name:
                    continue
                rel = img.relative_to(BASE)
                photos.append(str(rel).replace('\\', '/'))

    return photos


def find_satellite_for_site(site_id):
    """
    Find the satellite image for a site given its sequential shapefile ID.
    Images named like '10- Inago.png'.
    Returns relative path or empty string.
    """
    if not SATELLITE_DIR.exists():
        return ""

    prefix = str(int(site_id))
    for img in SATELLITE_DIR.iterdir():
        if img.is_file() and img.suffix.lower() == '.png':
            # Match files starting with the site number
            if re.match(rf'^0*{re.escape(prefix)}[-_ ]', img.name):
                return str(img.relative_to(BASE)).replace('\\', '/')

    return ""


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    if not KBA_JS.exists():
        sys.exit(f"❌  {KBA_JS} not found. Run convert_shapefile.py first.")
    if not FS_JSON.exists():
        sys.exit(f"❌  {FS_JSON} not found. Run extract_factsheets.py first.")

    # Load factsheet data
    factsheets = json.loads(FS_JSON.read_text(encoding='utf-8'))
    fs_keys = list(factsheets.keys())
    print(f"📋  Loaded {len(fs_keys)} factsheets")

    # Load kba-data.js — strip the JS wrapper to get JSON
    js_text = KBA_JS.read_text(encoding='utf-8')
    json_text = re.sub(r'^.*?var\s+KBA_GEOJSON\s*=\s*', '', js_text, flags=re.DOTALL)
    json_text = re.sub(r';\s*$', '', json_text.strip())
    geojson = json.loads(json_text)

    features = geojson['features']
    print(f"🗺   {len(features)} shapefile features to populate\n")

    unmatched = []
    for feat in features:
        p = feat['properties']
        shp_name = p.get('name', '')
        site_id  = p.get('site_id', '')

        # Match to factsheet
        key = best_match(shp_name, fs_keys)
        if key:
            fs = factsheets[key]
            en = fs.get('en', {})
            pt = fs.get('pt', {})

            # Overwrite fields from factsheet
            p['admin_region']            = en.get('admin_region', '')
            p['coordinates']             = en.get('coordinates', '')
            p['protection_category']     = en.get('protection_category', '')
            p['protection_category_pt']  = pt.get('protection_category', '')
            p['preexisting_designation'] = en.get('preexisting_designation', '')
            p['preexisting_designation_pt'] = pt.get('preexisting_designation', '')

            # Use factsheet criteria if shapefile has none
            if not p.get('kba_criteria'):
                p['kba_criteria'] = en.get('kba_criteria', '')

            p['description']    = en.get('description', '')
            p['description_pt'] = pt.get('description', '')
            p['kba_rationale']  = en.get('rationale', '')
            p['kba_rationale_pt'] = pt.get('rationale', '')

            # Use factsheet name (proper case) if available
            p['name_pt'] = fs.get('pt_site_name', '')

            # Threats
            en_threats = en.get('threats', [])
            if en_threats:
                p['threats'] = en_threats
            p['threats_pt'] = pt.get('threats', [])

            # Trigger species
            p['trigger_species']    = en.get('trigger_species', [])
            p['trigger_species_pt'] = pt.get('trigger_species', [])

            print(f"  ✅  {shp_name!r:40s} → '{key}'")
        else:
            print(f"  ⚠️   {shp_name!r:40s} → NO MATCH")
            unmatched.append(shp_name)

        # Photos and satellite (always by site_id)
        p['photos']          = find_photos_for_site(site_id)
        p['satellite_image'] = find_satellite_for_site(site_id)

    # Write updated kba-data.js
    header = (
        "// Auto-generated by convert_shapefile.py + populate_kba_data.py\n"
        "// Do not edit geometry by hand.\n\n"
    )
    js_out = header + "var KBA_GEOJSON = " + json.dumps(geojson, ensure_ascii=False, indent=2) + ";\n"
    OUTPUT.write_text(js_out, encoding='utf-8')

    print(f"\n🎉  Written to: {OUTPUT}")
    if unmatched:
        print(f"\n⚠️   Unmatched sites (no factsheet content): {unmatched}")
    else:
        print("✅  All sites matched to factsheet content.")


if __name__ == '__main__':
    main()
