# 🐚 Mangrove Tree Monitoring & Mapping

This Python script processes multiple geotagged tree monitoring databases, merges them with Google Sheets data, extracts GPS info from EXIF-tagged photos, and produces an interactive HTML map with download options for CSV, GeoJSON, and KML.

The script will build a web page with a Map, with 2 main layers : 
* Previous DB : it use all the db files (mysql db) present in the db folder and which come from all the local db exported from each volonteer Pijak app on their phones.
* Current DB: use the export db located in the Pijak DB tab on the linked Google Sheet file.

---

## 🗺️ What It Does

This tool:
- 🧩 Merges multiple local monitoring .db files from the Pijak mobile app
- 🔗 Connects to a Google Sheets document to fetch the centralized "Pijak DB" and "Tree Status"
- 📸 Extracts GPS metadata from EXIF-enabled photos (JPG/HEIC/PNG)
- 🧮 Computes health ratios (Alive/Dead) by location
- 🗺️ Generates an interactive map with image previews and filtering
- 📦 Outputs the data in CSV, GeoJSON, and KML formats
- ✅ Automatically downloads missing photos (PIJAK dataset)
- ✅ Exports final data to:
  - CSV
  - GeoJSON (full + Pijak-only)
  - KML (full + Pijak-only)
- ✅ Adds a beautiful Folium map with:
  - Favicon
  - Custom base layers (OpenStreetMap + Satellite)
  - Layer control
  - Search by tree code
  - Status filter (Alive / Dead / All)
  - Embedded legends and download menu

---

## 📂 Project Structure

```
.
├── db/                       # Folder with multiple .db SQLite files
├── pijak_foto/               # Folder with Pijak photos (can be filled automatically)
├── pictures/                 # Folder with EXIF-geotagged local images
├── pijak_translated.py       # Main Python script (this project)
├── tree_map.html             # Final interactive map
├── geotagged_tree_*.csv      # Intermediate CSVs (one per DB file)
├── geotagged_tree_aggregated_latest.csv
├── geotagged_tree.geojson    # Merged DB + Pijak GeoJSON
├── pijak_tree.geojson        # Pijak-only GeoJSON
├── geotagged_tree.kml        # Merged DB + Pijak KML
├── pijak_tree.kml            # Pijak-only KML
└── credentials.json          # Google Service Account JSON
```

---

## 🔧 Requirements

### ✅ Python Packages

Install with:

```bash
python3.10 -m venv pijak-venv
source pijak-venv/bin/activate
pip install pandas folium simplekml gspread oauth2client pillow ee geemap
```

Or, using `requirements.txt`:

```txt
pandas
folium
simplekml
gspread
google-auth
pillow
```

### ✅ System Dependencies

- `exiftool` (used to extract GPS coordinates from image metadata)

Install it with:

```bash
sudo apt install libimage-exiftool-perl
# or on macOS
brew install exiftool
```

---

## 🔐 Google Sheets Integration

1. Create a [Google Cloud Service Account](https://console.cloud.google.com/).
2. Share your spreadsheet (read-only) with the service account email.
3. Download the credentials file and rename it to `credentials.json`.

The following sheets are required:
- `Mangrove Database`
  - `TreeStatus`: 2-column table with `code`, `status`
  - `Pijak DB`: table with geotagged trees (`Kode`, `Latitude`, `Longitude`, `Tree Status`, `Foto 1`)

For generate TreeStatus we use the following Google Script which scan all the cell from the tab starting with "Group" and who contain each tag number with a checkbox on the right. If the checkbox is check the tree have been tagged and if the tag number cell have a color (background or text) different from default one, then the tree is dead.

For PijakDB, the table come directly from the CSV file coming from Pijak Dev Team. This table is enhanced with 3 new columns, when the Google Script is executed.

You can find the Google Sheet Script at the end.
---

## ▶️ Usage

```bash
python pijak_translated.py
```

This will:
- Process all `.db` files in the `db/` folder
- Extract EXIF GPS from `pictures/`
- Download and embed missing PIJAK photos
- Generate an interactive map: `tree_map.html`
- Export: CSV, GeoJSON (all and pijak-only), KML

---

## 📊 Outputs

| File                        | Description                             |
|----------------------------|-----------------------------------------|
| `tree_map.html`            | Final interactive map (OpenStreetMap)   |
| `geotagged_tree_*.csv`     | Intermediate DB-only CSVs               |
| `geotagged_tree_aggregated_latest.csv` | Merged and deduplicated latest tree info |
| `geotagged_tree.geojson`   | DB + PIJAK data as GeoJSON              |
| `pijak_tree.geojson`       | PIJAK-only trees                        |
| `geotagged_tree.kml`       | KML version of merged data              |
| `pijak_tree.kml`           | KML of PIJAK-only                       |

---

## 📌 Notes

- The map groups photos by GPS coordinates and displays full-sized thumbnails.
- Heatmap bins are ~10x10 meters based on rounded coordinates.
- Missing Pijak images are downloaded once and reused locally.

## Google Sheet Script

```javascript
function deleteColumnsWithHeaders() {
  const headersToDelete = ["JJK Code", "Tree Status", "Checkbox"]; // Headers to look for
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Pijak DB");
  if (!sheet) {
    Logger.log("Sheet 'Pijak DB' not found.");
    return;
  }  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];

  // Loop from right to left to avoid index shifting when deleting columns
  for (let col = headers.length - 1; col >= 0; col--) {
    if (headersToDelete.includes(headers[col])) {
      sheet.deleteColumn(col + 1); // +1 because sheet columns are 1-indexed
    }
  }
}

function countColoredCellsInAllGroupSheets() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const sheets = spreadsheet.getSheets();
  const targetRange = "A1:R101";
  let totalColoredJJK = 0;

  sheets.forEach(sheet => {
    const sheetName = sheet.getName();
    if (sheetName.startsWith("Group")) {
      const range = sheet.getRange(targetRange);
      const backgroundColors = range.getBackgrounds();
      const fontColors = range.getFontColors();
      const cellValues = range.getValues();

      for (let row = 0; row < backgroundColors.length; row++) {
        for (let col = 0; col < backgroundColors[row].length; col++) {
          const bg = backgroundColors[row][col].toLowerCase();
          const font = fontColors[row][col].toLowerCase();
          const value = String(cellValues[row][col]).trim();

          if (value.startsWith("JJK") && (bg !== "#ffffff" || font !== "#000000")) {
            totalColoredJJK++;
          }
        }
      }
    }
  });

  // Output the result in cell C2 of the active sheet
  spreadsheet.getActiveSheet().getRange("C2").setValue(`${totalColoredJJK}`);

  // Call the helper functions
  generateTreeStatus();
  generateTreeStatusPijak();
  enrichPijakDBfromTreeStatus();
  generateMissingTags();
}


function generateTreeStatus() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const sheets = spreadsheet.getSheets();
  const targetRange = "A1:R101";
  const result = [];

  // Process each "Group" sheet
  sheets.forEach(sheet => {
    const sheetName = sheet.getName();
    if (sheetName.startsWith("Group")) {
      const range = sheet.getRange(targetRange);
      const values = range.getValues();
      const backgroundColors = range.getBackgrounds();
      const fontColors = range.getFontColors();

      for (let row = 0; row < values.length; row++) {
        for (let col = 0; col < values[row].length - 1; col++) {
          const value = values[row][col];

          if (typeof value === 'string' && value.startsWith("JJK")) {
            const checkbox = values[row][col + 1];

            if (checkbox === true) {
              const bg = backgroundColors[row][col].toLowerCase();
              const font = fontColors[row][col].toLowerCase();
              const isDead = (bg !== "#ffffff" || font !== "#000000");

              result.push([value, isDead ? "Dead" : "Alive"]);
            }
          }
        }
      }
    }
  });

  // Output to the "TreeStatus" sheet
  let outputSheet = spreadsheet.getSheetByName("TreeStatus");
  if (outputSheet) {
    outputSheet.clear();
  } else {
    outputSheet = spreadsheet.insertSheet("TreeStatus");
  }

  // Write headers and data
  outputSheet.getRange(1, 1, 1, 2).setValues([["Tree ID", "Status"]]);
  if (result.length > 0) {
    outputSheet.getRange(2, 1, result.length, 2).setValues(result);
  }
}


function generateTreeStatusPijak() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const sheets = spreadsheet.getSheets();
  const targetRange = "A1:R101";
  const result = [];

  // Load data from "Pijak DB"
  const pijakSheet = spreadsheet.getSheetByName("Pijak DB");
  const pijakData = pijakSheet.getDataRange().getValues();

  // Build mapping: { MAN-x => Status }
  const pijakMap = {};
  const kodeIndex = pijakData[0].indexOf("Kode");
  const statusIndex = pijakData[0].indexOf("Status");

  for (let i = 1; i < pijakData.length; i++) {
    const kode = pijakData[i][kodeIndex];
    const status = pijakData[i][statusIndex];
    if (kode) pijakMap[String(kode).trim()] = status;
  }

  // Process each "Group" sheet
  sheets.forEach(sheet => {
    const sheetName = sheet.getName();
    if (sheetName.startsWith("Group")) {
      const range = sheet.getRange(targetRange);
      const values = range.getValues();
      const backgroundColors = range.getBackgrounds();
      const fontColors = range.getFontColors();

      for (let row = 0; row < values.length; row++) {
        for (let col = 0; col < values[row].length - 1; col++) {
          const value = values[row][col];

          if (typeof value === 'string' && value.startsWith("JJK-")) {
            const checkbox = values[row][col + 1];
            const isChecked = checkbox === true;

            const bg = backgroundColors[row][col].toLowerCase();
            const font = fontColors[row][col].toLowerCase();
            const isDead = (bg !== "#ffffff" || font !== "#000000");

            const status = isDead ? "Dead" : "Alive";
            const checkboxStatus = isChecked ? "Checked" : "Unchecked";

            // Convert JJK-001 to MAN-1, etc.
            const numericPart = value.replace("JJK-", "");
            const number = parseInt(numericPart, 10);
            const pijakCode = `MAN-${number}`;
            const pijakStatus = pijakMap[pijakCode] || "Not found";

            result.push([value, status, checkboxStatus, pijakStatus]);
          }
        }
      }
    }
  });

  // Output to the "TreeStatusPijak" sheet
  let outputSheet = spreadsheet.getSheetByName("TreeStatusPijak");
  if (outputSheet) {
    outputSheet.clear();
  } else {
    outputSheet = spreadsheet.insertSheet("TreeStatusPijak");
  }

  outputSheet.getRange(1, 1, 1, 4).setValues([
    ["Tree ID", "Status", "Checkbox", "Check Pijak"]
  ]);

  if (result.length > 0) {
    outputSheet.getRange(2, 1, result.length, 4).setValues(result);
  }
}


function enrichPijakDBfromTreeStatus() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const pijakSheet = ss.getSheetByName("Pijak DB");
  const statusSheet = ss.getSheetByName("TreeStatusPijak");

  if (!pijakSheet || !statusSheet) {
    throw new Error("One of the sheets 'Pijak DB' or 'TreeStatusPijak' is missing.");
  }

  deleteColumnsWithHeaders();
  
  // Step 1: Read headers
  let header = pijakSheet.getRange(1, 1, 1, pijakSheet.getLastColumn()).getValues()[0];
  const kodeIndex = header.indexOf("Kode");
  if (kodeIndex === -1) throw new Error("'Kode' column not found in 'Pijak DB'.");

  // Step 2: Add missing columns
  const additionalColumns = ["JJK Code", "Tree Status", "Checkbox"];
  const missingColumns = additionalColumns.filter(col => !header.includes(col));
  const updatedHeader = [...header, ...missingColumns];

  // Step 3: Build map from TreeStatusPijak
  const statusData = statusSheet.getDataRange().getValues();
  const statusHeader = statusData[0];
  const jjkIndex = statusHeader.indexOf("Tree ID");
  const statusIndex = statusHeader.indexOf("Status");
  const checkboxIndex = statusHeader.indexOf("Checkbox");

  const treeStatusMap = {};
  for (let i = 1; i < statusData.length; i++) {
    const jjk = statusData[i][jjkIndex];
    const status = statusData[i][statusIndex];
    const checkbox = statusData[i][checkboxIndex];
    treeStatusMap[jjk] = { status, checkbox };
  }

  // Step 4: Read existing data
  const pijakData = pijakSheet.getRange(2, 1, pijakSheet.getLastRow() - 1, header.length).getValues();
  const newData = [updatedHeader];


  for (let i = 0; i < pijakData.length; i++) {
    const row = pijakData[i];
    const kode = row[kodeIndex];
    const rowCopy = [...row];

    // Convert MAN-x to JJK-xxx
    const number = parseInt(kode.replace("MAN-", ""), 10);
    const jjkCode = `JJK-${String(number).padStart(3, "0")}`;

    const treeData = treeStatusMap[jjkCode] || { status: "Not found", checkbox: "Not found" };

    // Add new columns only if they were not in original header
    if (!header.includes("JJK Code")) rowCopy.push(jjkCode);
    if (!header.includes("Tree Status")) rowCopy.push(treeData.status);
    if (!header.includes("Checkbox")) rowCopy.push(treeData.checkbox);

    newData.push(rowCopy);
  }

  // Step 5: Final write
  pijakSheet.clearContents();

  const rowCount = newData.length;
  const colCount = newData[0].length;

  if (colCount > pijakSheet.getMaxColumns()) {
    pijakSheet.insertColumnsAfter(pijakSheet.getMaxColumns(), colCount - pijakSheet.getMaxColumns());
  }

  pijakSheet.getRange(1, 1, rowCount, colCount).setValues(newData);

  SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Total").getRange("C8").setFormula('=COUNTIFS(\'Pijak DB\'!K:K, "Dead", \'Pijak DB\'!F:F, "Geotaged")');
  SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Total").getRange("F11").setFormula('=COUNTIFS(\'Pijak DB\'!L:L, "Unchecked", \'Pijak DB\'!F:F, "Kosong")');
  SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Total").getRange("F13").setFormula('=COUNTIFS(\'Pijak DB\'!L:L, "Checked", \'Pijak DB\'!F:F, "Kosong")');
}

function generateMissingTags() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const sheets = spreadsheet.getSheets();
  const targetRange = "A1:R101";
  const result = [];

  const backlogSheet = spreadsheet.getSheetByName("Tags still not deployed (backlog)");
  const backlogValues = backlogSheet.getDataRange().getValues().flat();

  const waterSheet = spreadsheet.getSheetByName("Tags found in water");
  const waterValues = waterSheet.getDataRange().getValues().flat();

  sheets.forEach(sheet => {
    const sheetName = sheet.getName();
    if (sheetName.startsWith("Group")) {
      const range = sheet.getRange(targetRange);
      const values = range.getValues();

      for (let row = 0; row < values.length; row++) {
        for (let col = 0; col < values[row].length - 1; col++) {
          const value = values[row][col];

          if (typeof value === 'string' && value.startsWith("JJK")) {
            const checkbox = values[row][col + 1];

            if (checkbox === false) {
              const inBacklog = backlogValues.includes(value);
              const inWater = waterValues.includes(value);

              const needToLaminate = !(inBacklog || inWater);

              result.push([value, "No", inBacklog, inWater, needToLaminate]);
            }
          }
        }
      }
    }
  });

  let outputSheet = spreadsheet.getSheetByName("Tags Missing (need to laminate)");
  if (outputSheet) {
    outputSheet.clear();
  } else {
    outputSheet = spreadsheet.insertSheet("Tags Missing (need to laminate)");
  }

  outputSheet.getRange(1, 1, 1, 5).setValues([["Tree ID", "Taged ?", "In backlog?", "Found in water?", "Need to laminate?"]]);

  if (result.length > 0) {
    outputSheet.getRange(2, 1, result.length, 5).setValues(result);
  }
}


```
---

## 📸 Credits

- Map tiles © [OpenStreetMap](https://www.openstreetmap.org/)
- Satellite tiles © ESRI
- Photography by ©Lucas Lamy (@lcsframes on instagram)
- Developed for mangrove restoration and monitoring projects

---

## 🪵 License

MIT License – use freely with attribution.

This project is licensed for environmental, academic, and nonprofit use only.

---

## 👤 Author

**Lucas Lamy**  
Tree mapping automation and photography enthusiast 🌱  
2025

---
