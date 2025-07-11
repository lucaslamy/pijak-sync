
# 🗺️ pyjak-sync : Geotagged Tree Monitoring Map Generator

This project processes multiple SQLite `.db` files containing geotagged tree monitoring data. It cleans and aggregates the data, enriches it using a Google Sheet (tree status), and generates:

- ✅ A cleaned CSV file
- 🌍 A KML file for GIS tools
- 🧭 A GeoJSON file for mapping applications
- 🖥️ An interactive HTML map with live search, legends, and download options

---

## 📁 Folder Structure

```
project/
│
├── db/                             # Folder containing all .db files
├── credentials.json                # Google service account file
├── script.py                       # Main Python script
├── geotagged_tree_aggregated_latest.csv
├── geotagged_tree.kml
├── geotagged_tree.geojson
└── tree_map.html                   # Interactive map
```

---

## 🚀 Features

- ✅ Supports multiple SQLite databases
- ✅ Automatically formats codes (`MAN-1` → `JJK-001`)
- ✅ Merges latest Google Sheet statuses
- ✅ Generates color-coded map based on tree status
- ✅ Adds interactive HTML search and legend
- ✅ Outputs in CSV, KML, and GeoJSON formats

---

## 🔐 Google Sheets API Setup

1. Create a Google Cloud project.
2. Enable:
   - **Google Sheets API**
   - **Google Drive API**
3. Create a **Service Account** and download `credentials.json`
4. Share your Google Sheet with the service account email.

The sheet must contain a `TreeStatus` worksheet with:

| code    | status  |
|---------|---------|
| JJK-001 | Alive   |
| JJK-002 | Dead    |

---

## 📦 Requirements

Install the required Python libraries:

```bash
pip install pandas folium simplekml gspread google-auth
```

---

## 🛠️ Running the Script

```bash
python script.py
```

After running:

- `tree_map.html` will be created with your interactive map
- You’ll also get `.csv`, `.kml`, and `.geojson` exports

---

## 🎨 Status Colors (Legend)

| Status   | Color     |
|----------|-----------|
| Dead     | 🟥 Red     |
| Alive    | 🟩 Green   |
| Unknown  | ⬜ Gray    |

---

## 🔍 Map Search Feature

Use the search box on the map to search for a tree by its code (e.g. `JJK-017`). Press `Enter` to locate and zoom to that tree.

---

## 📥 Downloadable from Map UI

From the interactive map, you can download:

- 📄 `geotagged_tree_aggregated_latest.csv`
- 🌍 `geotagged_tree.kml`

These files are linked directly in the map interface.

---

## 🔄 Processing Logic

- Reads all `.db` files in `/db`
- Applies SQL query to extract tree + monitoring info
- Filters out rows with `statusApproval = 'NeedAction'`
- Normalizes and deduplicates codes by latest date
- Fetches external status from Google Sheets
- Builds interactive map with colored markers and search
- Exports to CSV, KML, and GeoJSON

---

## 👤 Author

**Lucas Lamy**  
Tree mapping automation and photography enthusiast 🌱  
2025

---

## 📜 License

MIT License – use freely with attribution.
