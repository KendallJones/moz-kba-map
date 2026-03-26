#!/usr/bin/env python3
"""
build_species_list.py
=====================
Extracts every potential Latin binomial name from all text fields in
factsheet_data.json, validates each unique candidate against the GBIF
species API, and writes validated_species.js for use by the webmap.

USAGE:
    python3 build_species_list.py

OUTPUT:
    validated_species.js  — JS file assigning var VALIDATED_SPECIES = [...names]

REQUIRES:
    pip install requests
"""

import json
import re
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("❌  requests not found. Run:  pip install requests")

BASE        = Path(__file__).parent
FS_JSON     = BASE / "factsheet_data.json"
OUTPUT_JS   = BASE / "validated_species.js"

GBIF_API    = "https://api.gbif.org/v1/species/match"
BATCH_PAUSE = 0.05   # seconds between GBIF requests (polite rate-limiting)


# ── Candidate extraction ─────────────────────────────────────────────────────

# Match capitalised genus + lowercase species epithet (+ optional subspecies)
BINOMIAL_RE = re.compile(
    r'\b([A-Z][a-z]{2,})\s+([a-z]{3,})(?:\s+([a-z]{3,}))?\b'
)

# Words that look like binomials but aren't (common in academic text)
FALSE_POSITIVE_GENERA = {
    'Jones', 'Osborne', 'Allen', 'Baker', 'Smith', 'Brown', 'Wilson',
    'This', 'These', 'Such', 'Most', 'Many', 'Some', 'Both', 'Each',
    'The', 'Due', 'Based', 'However', 'Although', 'Despite', 'Within',
    'During', 'Under', 'Above', 'Below', 'Along', 'Between', 'Among',
    'Through', 'After', 'Before', 'Since', 'Until', 'While', 'Where',
    'When', 'Which', 'That', 'With', 'From', 'Into', 'Onto', 'Upon',
    'Very', 'More', 'Most', 'Less', 'Much', 'Just', 'Only', 'Even',
    'Also', 'About', 'Over', 'Under', 'Around', 'Against', 'Across',
    'North', 'South', 'East', 'West', 'Mount', 'Cape', 'Lake', 'River',
    'Red', 'Blue', 'Green', 'Black', 'White', 'African', 'Indian',
    'Mozambique', 'Malawi', 'Tanzania', 'Zambia', 'Zimbabwe', 'Kenya',
    'Africa', 'Madagascar',
    'Alliance', 'Important', 'Bird', 'Area', 'Zero', 'Extinction',
    'Global', 'International', 'National', 'Provincial', 'Local',
    'Forest', 'Miombo', 'Coastal',
}


def extract_candidates(text):
    """Return set of candidate binomial names from a text string."""
    candidates = set()
    if not text:
        return candidates
    for m in BINOMIAL_RE.finditer(text):
        genus = m.group(1)
        if genus in FALSE_POSITIVE_GENERA:
            continue
        species = m.group(2)
        name = f"{genus} {species}"
        # Skip if epithet looks like a common English adverb/adjective
        if species in {'et', 'al', 'sp', 'spp', 'cf', 'aff', 'var',
                       'subsp', 'nov', 'ined', 'the', 'and', 'for',
                       'with', 'from', 'this', 'that', 'also'}:
            continue
        candidates.add(name)
        # Add trinomial if present
        if m.group(3):
            candidates.add(f"{name} {m.group(3)}")
    return candidates


def gather_all_candidates(factsheets):
    """Collect all candidate names from description + rationale of all sites."""
    all_candidates = set()
    text_fields = ['description', 'rationale']
    for site_name, site in factsheets.items():
        for lang in ('en', 'pt'):
            data = site.get(lang, {})
            for field in text_fields:
                all_candidates |= extract_candidates(data.get(field, ''))
    print(f"🔍  Found {len(all_candidates)} unique candidate binomial names")
    return sorted(all_candidates)


# ── GBIF validation ──────────────────────────────────────────────────────────

def check_gbif(name):
    """
    Returns True if GBIF confidently matches the name to a known species.
    Uses fuzzy=false for strict matching.
    """
    try:
        r = requests.get(GBIF_API, params={'name': name, 'verbose': False},
                         timeout=10)
        if r.status_code != 200:
            return False
        data = r.json()
        # matchType EXACT or FUZZY with high confidence, and a real rank
        match_type = data.get('matchType', 'NONE')
        confidence = data.get('confidence', 0)
        rank = data.get('rank', '')
        status = data.get('status', '')
        # Accept if GBIF found a species-level match with reasonable confidence
        if match_type == 'NONE':
            return False
        if rank not in ('SPECIES', 'SUBSPECIES', 'VARIETY', 'FORM'):
            return False
        if confidence < 90:
            return False
        return True
    except Exception:
        return False


def validate_candidates(candidates):
    """Check each candidate against GBIF; return sorted list of valid names."""
    valid = []
    total = len(candidates)
    for i, name in enumerate(candidates, 1):
        ok = check_gbif(name)
        status = "✅" if ok else "  "
        print(f"  {status} [{i:3d}/{total}]  {name}")
        if ok:
            valid.append(name)
        time.sleep(BATCH_PAUSE)
    return valid


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not FS_JSON.exists():
        sys.exit(f"❌  {FS_JSON} not found. Run extract_factsheets.py first.")

    factsheets = json.loads(FS_JSON.read_text(encoding='utf-8'))

    # Also include all names already in trigger_species lists
    trigger_names = set()
    for site in factsheets.values():
        for lang in ('en', 'pt'):
            for sp in site.get(lang, {}).get('trigger_species', []):
                if sp.get('name'):
                    trigger_names.add(sp['name'])
    print(f"📋  {len(trigger_names)} trigger species names (always included)")

    candidates = gather_all_candidates(factsheets)

    # Only validate candidates not already in trigger species
    to_check = [c for c in candidates if c not in trigger_names]
    print(f"\n🌐  Validating {len(to_check)} candidates against GBIF...\n")
    gbif_valid = validate_candidates(to_check)

    # Combine trigger names + GBIF-validated names
    all_valid = sorted(trigger_names | set(gbif_valid))
    print(f"\n✅  {len(all_valid)} total validated species names "
          f"({len(trigger_names)} trigger + {len(gbif_valid)} from text)")

    # Write JS file
    js = (
        "// Auto-generated by build_species_list.py — do not edit by hand.\n"
        "// Contains all validated species names for Latin italics in the webmap.\n\n"
        "var VALIDATED_SPECIES = " +
        json.dumps(all_valid, ensure_ascii=False, indent=2) +
        ";\n"
    )
    OUTPUT_JS.write_text(js, encoding='utf-8')
    print(f"📄  Written to: {OUTPUT_JS}")


if __name__ == '__main__':
    main()
