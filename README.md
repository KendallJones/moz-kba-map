# Mozambique KBA Web Map — Setup Guide

A fully offline-capable interactive map of Key Biodiversity Areas in Mozambique,
built with Leaflet.js. No account or API key needed.

---

## Folder Structure

```
mozambique-kba-map/
├── index.html            ← The web map (open this in a browser)
├── kba-data.js           ← Your KBA site data (GeoJSON + site info)
├── convert_shapefile.py  ← Script to convert your shapefile → kba-data.js
├── README.md             ← This file
└── images/               ← Put your site photos here
    ├── gorongosa-1.jpg
    ├── quirimbas-1.jpg
    └── ...
```

---

## Step 1 — Convert your Shapefile to GeoJSON

You need Python 3 with `geopandas` installed.

```bash
pip install geopandas
```

**First, check what column names are in your shapefile:**

```bash
python convert_shapefile.py --list-fields --input "/Users/kendalljones/Library/CloudStorage/OneDrive-WildlifeConservationSociety/Documents/WCS_2018/Misc_work/Moz_KBA_webmap/Data/KBAs_MZ.shp"
```

This will print all field names. Then open `convert_shapefile.py` and edit the
`FIELD_MAP` section near the top to match your shapefile's column names:

```python
FIELD_MAP = {
    "SiteName":   "name",      # ← change "SiteName" to your actual column name
    "Province":   "region",
}
```

**Then run the conversion:**

```bash
python convert_shapefile.py --input path/to/your_kba_file.shp --output kba-data.js
```

This will overwrite `kba-data.js` with all your real site geometries.

---

## Step 2 — Add Site Information

Open `kba-data.js`. For each feature, fill in the properties:

```js
"properties": {
  "name": "Gorongosa Mountain",         // Site name (may come from shapefile)
  "region": "Sofala Province",          // Province or region

  "description": "A paragraph describing the site...",

  "kba_rationale": "Why this site qualifies as a KBA...",

  "threats": [
    "Agricultural encroachment",
    "Charcoal production"
  ],

  "trigger_species": [
    {
      "common_name": "Swynnerton's Robin",
      "scientific": "Swynnertonia swynnertoni",
      "iucn_status": "Vulnerable",
      "icon": "🐦"           // Any emoji works here
    }
  ],

  "photos": [
    "images/gorongosa-1.jpg",
    "images/gorongosa-2.jpg"
  ]
}
```

---

## Step 3 — Add Photos

1. Create an `images/` folder inside `mozambique-kba-map/`.
2. Copy your site photos there (JPG or PNG).
3. Reference them in `kba-data.js` as `"images/your-photo.jpg"`.

Photo tips:
- Landscape orientation works best (the panel shows a 220px tall photo strip).
- Aim for files under 500 KB for fast loading.
- You can have multiple photos per site — thumbnails will appear automatically.

---

## Step 4 — Run Locally

Because the map loads a `.js` data file, you need to run it through a local
web server (browsers block local file access for security reasons).

**Option A — Python (easiest):**
```bash
cd mozambique-kba-map
python -m http.server 8000
```
Then open: http://localhost:8000

**Option B — VS Code:**
Install the "Live Server" extension, right-click `index.html` → Open with Live Server.

**Option C — Node.js:**
```bash
npx serve .
```

---

## Step 5 — Deploy Online (optional)

To share the map publicly with no server costs:

**GitHub Pages (free):**
1. Create a free GitHub account at github.com
2. Create a new repository (e.g. `moz-kba-map`)
3. Upload all files in this folder
4. Go to Settings → Pages → Source: main branch → Save
5. Your map will be live at `https://yourusername.github.io/moz-kba-map/`

**Netlify (free, drag-and-drop):**
1. Go to https://netlify.com and sign up free
2. Drag your entire `mozambique-kba-map/` folder onto the deploy area
3. You get a public URL instantly

---

## Customisation

| What                        | Where to change                          |
|-----------------------------|------------------------------------------|
| Map centre / zoom           | `index.html` → `L.map(..., {center, zoom})` |
| KBA polygon colour          | `index.html` → `styleDefault`            |
| Selected polygon colour     | `index.html` → `styleSelected`           |
| Base map style              | Replace the CartoDB tile URL with any    |
|                             | free Leaflet provider (see leaflet-providers.js) |
| Panel width                 | `index.html` → `--panel-w` CSS variable  |
| Add new popup fields        | `kba-data.js` properties + `index.html` `openPanel()` function |

---

## Troubleshooting

**"kba-data.js not found" error:**
Make sure `kba-data.js` is in the same folder as `index.html`.

**Map is blank / no polygons:**
Open your browser's developer console (F12). Check for errors. The most common
cause is running index.html by double-clicking instead of through a local server.

**Photos not showing:**
Check the file paths in `kba-data.js` match the actual filenames in your `images/`
folder. Paths are case-sensitive on Linux/Mac.

**Shapefile conversion fails:**
Make sure all four shapefile components are in the same folder:
`yourfile.shp`, `yourfile.dbf`, `yourfile.prj`, `yourfile.shx`
