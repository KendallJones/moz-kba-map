#!/usr/bin/env python3
"""
extract_factsheets.py
=====================
Parses the English and Portuguese KBA factsheet PDFs and extracts
structured content for all 30 sites.

OUTPUT: factsheet_data.json — keyed by site_id, with 'en' and 'pt' sub-objects.

USAGE:
    python3 extract_factsheets.py
"""

import json
import re
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("PyMuPDF not found. Run: pip install pymupdf")

try:
    from PIL import Image
    import numpy as np
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

BASE = Path(__file__).parent
ATLAS = BASE / "Moz KBAs_Atlas" / "00_Factsheets_PT&EN_VOL II"

EN_PDF = ATLAS / "KBAs_Factsheet_eng vol ii _Actualizado Junho 2021.pdf"
PT_PDF = ATLAS / "Ficha Tecnica das KBAs_Port vol ii_Actualizado_Junho 2021 .pdf"

OUTPUT = BASE / "factsheet_data.json"

# ── Per-species icon extraction ───────────────────────────────────────────────
# Each species has its own silhouette in the PDF (e.g. elephant, hippo, lion…).
# Icons share a fill colour per taxonomic group but differ in shape.
# We render each icon individually and cache by species-name slug.

KNOWN_FILL_GROUPS = {
    (0.40, 0.40, 0.50): 'bird',
    (0.60, 0.51, 0.44): 'reptile',
    (0.05, 0.17, 0.11): 'mammal',
    (0.29, 0.58, 0.79): 'fish',
    (0.61, 0.61, 0.21): 'amphibian',
    (0.42, 0.54, 0.46): 'plant',
}

ICON_RENDER_MAT = fitz.Matrix(6, 6)
SPECIES_ICONS_DIR = BASE / "icons" / "species"
_icon_slug_cache: dict = {}   # slug → relative web path (avoid re-rendering)


def _is_known_fill(fill, tol=0.06):
    if not fill or len(fill) < 3:
        return False
    return any(all(abs(fill[i] - ref[i]) < tol for i in range(3))
               for ref in KNOWN_FILL_GROUPS)


def _slugify(name):
    return re.sub(r'[^a-z0-9]+', '_', name.strip().lower()).strip('_')


def _remove_bg(pix):
    """Make the sandy PDF background transparent."""
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples).convert("RGBA")
    data = np.array(img)
    r, g, b = data[:, :, 0], data[:, :, 1], data[:, :, 2]
    data[:, :, 3] = np.where((r > 200) & (g > 190) & (b > 170), 0, 255)
    return Image.fromarray(data)


def extract_species_icons(fitz_page, trigger_species):
    """
    For each species in trigger_species, find the matching silhouette drawing
    on the page (by y-position proximity), render it as a transparent PNG and
    save to icons/species/<slug>.png.  Adds an 'icon' key to each species dict.
    """
    if not HAS_PIL:
        return

    # Collect candidate icon drawings (small filled shapes)
    icon_drawings = []
    for d in fitz_page.get_drawings():
        r = d['rect']
        if not _is_known_fill(d.get('fill')):
            continue
        w, h = r.width, r.height
        if 5 < w < 35 and 4 < h < 30:
            icon_drawings.append({'rect': r, 'y': (r.y0 + r.y1) / 2})

    if not icon_drawings:
        return

    # Build y-position index from species text spans on the page
    text_dict = fitz_page.get_text("dict")
    species_spans = []
    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                txt = span["text"].strip()
                if "AvenirNextCondensed-Demi" in span.get("font", "") and len(txt) > 4 and ' ' in txt:
                    species_spans.append({'text': txt, 'y': (span["bbox"][1] + span["bbox"][3]) / 2})

    SPECIES_ICONS_DIR.mkdir(parents=True, exist_ok=True)

    for sp in trigger_species:
        name = sp.get('name', '')
        if not name:
            continue
        slug = _slugify(name)

        # Use cached path if already rendered
        if slug in _icon_slug_cache:
            sp['icon'] = _icon_slug_cache[slug]
            continue

        # Find the text span for this species
        matching_span = next(
            (s for s in species_spans if name in s['text'] or s['text'] in name),
            None
        )
        if not matching_span:
            continue

        # Find the closest icon drawing by y position
        closest = min(icon_drawings, key=lambda d: abs(d['y'] - matching_span['y']))
        if abs(closest['y'] - matching_span['y']) > 15:
            continue

        # Render and save
        r = closest['rect']
        clip = fitz.Rect(r.x0 - 1, r.y0 - 1, r.x1 + 1, r.y1 + 1)
        pix = fitz_page.get_pixmap(matrix=ICON_RENDER_MAT, clip=clip)
        img = _remove_bg(pix)
        img.save(str(SPECIES_ICONS_DIR / f"{slug}.png"))

        rel_path = f"icons/species/{slug}.png"
        _icon_slug_cache[slug] = rel_path
        sp['icon'] = rel_path

# Pages where factsheets start (0-indexed). Both PDFs start at page 11.
FACTSHEET_START_PAGE = 11

# ── English field labels ────────────────────────────────────────────────────
EN_LABELS = {
    "admin_region":           r"Admin Region:\s*(.+)",
    "kba_area":               r"KBA Area:\s*(.+)",
    "coordinates":            r"Coordinates:\s*(.+)",
    "protection_category":    r"current protection category:\s*(.+)",
    "preexisting_designation":r"pre-existing designation:\s*(.+)",
    "kba_criteria":           r"kba criteria triggered:\s*(.+)",
    "site_id":                r"SITE ID:\s*(\d+)",
}
EN_SECTIONS = {
    "description":    "Site description",
    "trigger_species":"trigger species",
    "threats":        "main threats",
}
EN_RATIONALE_HEADER = "rationale"
EN_REFERENCES_HEADER = "references"

# ── Portuguese field labels ─────────────────────────────────────────────────
PT_LABELS = {
    "admin_region":           r"Região Admin:\s*(.+)",
    "kba_area":               r"Área da KBA:\s*(.+)",
    "coordinates":            r"Coordenadas:\s*(.+)",
    "protection_category":    r"Categoria actual de protecção:\s*(.+)",
    "preexisting_designation":r"designação pré-existentes:\s*(.+)",
    "kba_criteria":           r"Critérios KBA activados:\s*(.+)",
    "site_id":                r"Código:\s*(\d+)",
}
PT_SECTIONS = {
    "description":    "Descrição do local",
    "trigger_species":"Espécies que activaram os critérios",
    "threats":        "Principais ameaças no local",
}
PT_RATIONALE_HEADER = "Fundamentação"
PT_REFERENCES_HEADER = "referências"


def clean(text):
    """Remove excess whitespace and fix common PDF artifacts."""
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    # Rejoin hyphenated line breaks
    text = re.sub(r'-\n(\w)', r'\1', text)
    return text.strip()


def extract_labeled_fields(text, labels):
    """Extract single-line labeled fields using regex patterns."""
    result = {}
    for key, pattern in labels.items():
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            result[key] = m.group(1).strip()
    return result


def extract_sections(text, sections_map, rationale_header, references_header):
    """
    Extract text sections between known headers.
    Returns dict with description, trigger_species (list), threats (list),
    and rationale.
    """
    text_lower = text.lower()
    result = {}

    keys = list(sections_map.keys())
    headers = list(sections_map.values())

    for i, (key, header) in enumerate(zip(keys, headers)):
        start = text_lower.find(header.lower())
        if start == -1:
            result[key] = ""
            continue
        start += len(header)

        # End is next section header or end of text
        end = len(text)
        for next_header in headers[i+1:] + [rationale_header, references_header, "SITE ID", "Código"]:
            pos = text_lower.find(next_header.lower(), start)
            if pos != -1:
                end = min(end, pos)
                break

        section_text = clean(text[start:end])
        result[key] = section_text

    return result


def parse_trigger_species(raw_text):
    """
    Parse trigger species text into list of dicts with name and iucn_status.
    Lines look like: 'Loxodonta africana EN' or 'Cordylus meculae LC (NOTE)'
    """
    species_list = []
    if not raw_text:
        return species_list

    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
    iucn_statuses = {'CR', 'EN', 'VU', 'NT', 'LC', 'DD', 'EX', 'EW'}

    for line in lines:
        # Skip photo captions / short lines / lines that are just image labels
        if len(line) < 5:
            continue
        # Try to extract IUCN status from the line
        tokens = line.split()
        iucn = None
        for token in tokens:
            clean_token = token.rstrip('.,;()')
            if clean_token in iucn_statuses:
                iucn = clean_token
                break

        if iucn:
            # Species name is everything before the IUCN status
            idx = line.find(iucn)
            name = line[:idx].strip().rstrip('.,;')
            note_match = re.search(r'\(([^)]+)\)', line[idx:])
            note = note_match.group(1) if note_match else ""
            entry = {"name": name, "iucn_status": iucn}
            if note:
                entry["note"] = note
            species_list.append(entry)

    return species_list


def parse_threats(raw_text):
    """Split threats text into a list, using commas as the delimiter."""
    if not raw_text:
        return []

    # Remove scale-bar lines: lone numbers or patterns like "0", "5 km", "2 miles"
    lines = raw_text.split('\n')
    kept = []
    for line in lines:
        s = line.strip()
        if re.match(r'^\d+(\s*(km|miles?))?\s*$', s, re.IGNORECASE):
            continue
        kept.append(s)

    # Join lines (PDF wraps long threat strings across lines)
    joined = ' '.join(kept)

    # Split on commas; also honour semicolons as separators
    parts = re.split(r'[,;]', joined)
    threats = []
    for p in parts:
        p = p.strip()
        if len(p) > 3:
            threats.append(p[0].upper() + p[1:].lower())
    return threats


def extract_rationale(page2_text, rationale_header, references_header):
    """Extract rationale from the second page of a factsheet."""
    text_lower = page2_text.lower()
    rat_pos = text_lower.find(rationale_header.lower())
    if rat_pos == -1:
        return ""
    rat_start = rat_pos + len(rationale_header)

    # Rationale ends at references or end of page
    ref_pos = text_lower.find(references_header.lower(), rat_start)
    if ref_pos == -1:
        rat_text = page2_text[rat_start:]
    else:
        rat_text = page2_text[rat_start:ref_pos]

    return clean(rat_text)


def extract_site_name(page_text):
    """
    The site name is the first prominent line after the page number.
    It appears before 'KBA' / 'KEY BIODIVERSITY AREAS'.
    """
    lines = [l.strip() for l in page_text.split('\n') if l.strip()]
    # Skip the page number (first line, usually just digits)
    for i, line in enumerate(lines):
        if re.match(r'^\d+$', line):
            # Next non-empty line is the site name
            for candidate in lines[i+1:]:
                if candidate.upper() in ('KBA', 'KEY BIODIVERSITY AREAS', '0'):
                    break
                if len(candidate) > 2:
                    return candidate
    return ""


def process_pdf(pdf_path, labels, sections_map, rationale_hdr, references_hdr, lang):
    """Process one PDF and return dict keyed by site_id."""
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    sites = {}

    page_idx = FACTSHEET_START_PAGE
    while page_idx < total_pages - 1:
        page1_text = doc[page_idx].get_text()
        page2_text = doc[page_idx + 1].get_text() if page_idx + 1 < total_pages else ""

        # Check if this looks like a factsheet page (has a site ID or known header)
        has_site_id = re.search(labels.get("site_id", r"SITE ID:\s*\d+"), page1_text, re.IGNORECASE)
        has_section = any(s.lower() in page1_text.lower() for s in sections_map.values())

        if not (has_site_id or has_section):
            page_idx += 1
            continue

        site_name = extract_site_name(page1_text)
        fields = extract_labeled_fields(page1_text, labels)
        sections = extract_sections(page1_text, sections_map, rationale_hdr, references_hdr)
        rationale = extract_rationale(page2_text, rationale_hdr, references_hdr)

        site_id = fields.get("site_id", "")
        trigger_species = parse_trigger_species(sections.get("trigger_species", ""))

        # PDF column layout often pushes the species list to after "SITE ID: XXXXX"
        # (EN) or "Código: XXXXX" (PT). Scan that tail and merge any extra species.
        site_id_m = re.search(r'(?:SITE ID|C[oó]digo):\s*\n?\s*\d+\n', page1_text, re.IGNORECASE)
        if site_id_m:
            tail_text = page1_text[site_id_m.end():]
            extra = parse_trigger_species(clean(tail_text))
            existing_names = {s['name'] for s in trigger_species}
            for sp in extra:
                if sp['name'] not in existing_names:
                    trigger_species.append(sp)
                    existing_names.add(sp['name'])

        # Attach per-species silhouette icons (renders each icon as a PNG)
        extract_species_icons(doc[page_idx], trigger_species)

        threats = parse_threats(sections.get("threats", ""))

        site_data = {
            "site_name": site_name,
            "admin_region": fields.get("admin_region", ""),
            "kba_area": fields.get("kba_area", ""),
            "coordinates": fields.get("coordinates", ""),
            "protection_category": fields.get("protection_category", ""),
            "preexisting_designation": fields.get("preexisting_designation", ""),
            "kba_criteria": fields.get("kba_criteria", ""),
            "description": sections.get("description", ""),
            "trigger_species": trigger_species,
            "threats": threats,
            "rationale": rationale,
        }

        # Key by page number so EN and PT versions (on identical page positions)
        # can be merged, regardless of differing site name translations.
        page_key = page_idx + 1  # 1-indexed page number
        sites[page_key] = site_data
        sites[page_key]["kba_secretariat_id"] = site_id
        print(f"  [{lang}] p{page_key}: {site_name!r}")

        page_idx += 2  # Each factsheet is 2 pages

    return sites


def main():
    print(f"📄  Extracting English factsheets from:\n    {EN_PDF.name}")
    en_sites = process_pdf(EN_PDF, EN_LABELS, EN_SECTIONS, EN_RATIONALE_HEADER, EN_REFERENCES_HEADER, "EN")

    print(f"\n📄  Extracting Portuguese factsheets from:\n    {PT_PDF.name}")
    pt_sites = process_pdf(PT_PDF, PT_LABELS, PT_SECTIONS, PT_RATIONALE_HEADER, PT_REFERENCES_HEADER, "PT")

    # Merge EN and PT by page number (identical in both PDFs)
    all_pages = sorted(set(en_sites.keys()) | set(pt_sites.keys()))

    merged = {}
    for page in all_pages:
        en = en_sites.get(page, {})
        pt = pt_sites.get(page, {})
        # Use the EN site name as the primary match key for populate_kba_data.py
        en_name = en.get("site_name", "")
        pt_name = pt.get("site_name", "")
        merged[en_name] = {
            "en": en,
            "pt": pt,
            "pt_site_name": pt_name,
            "page": page,
        }

    OUTPUT.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n✅  Wrote {len(merged)} sites to: {OUTPUT}")
    for name, data in merged.items():
        pt_name = data.get("pt_site_name", "")
        print(f"  p{data['page']:2d}  EN: {name!r:35s}  PT: {pt_name!r}")


if __name__ == "__main__":
    main()
