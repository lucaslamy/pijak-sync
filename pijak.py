import sqlite3
import pandas as pd
import folium
from folium.plugins import Fullscreen
from folium import Element
import simplekml
import json
import os
from glob import glob
import gspread
from google.oauth2.service_account import Credentials

# 🔧 Output paths
output_csv = "geotagged_tree_aggregated_latest.csv"
output_geojson = "geotagged_tree.geojson"
output_kml = "geotagged_tree.kml"

# 📁 Folder with .db files
db_folder = './db'
csv_files = []

# 📄 SQL Query
query = """
SELECT
    t.id AS tree_id,
    t.code,
    t.name AS tree_name,
    t.binomialName,
    t.status AS tree_status,
    t.programName,
    tm.treeMonitoringId,
    tm.date AS monitoring_date,
    tm.latitude AS latitude,
    tm.longitude AS longitude,
    tm.elevation AS monitoring_elevation,
    tm.statusApproval,
    tm.img1
FROM tree t
JOIN tree_monitoring tm ON t.id = tm.treeId;
"""

# 🔁 Process each .db
db_paths = glob(os.path.join(db_folder, "*.db"))
if not db_paths:
    print("❌ No .db files found.")
    exit(1)

for db_path in db_paths:
    db_name = os.path.splitext(os.path.basename(db_path))[0]
    out_csv = f"geotagged_tree_{db_name}.csv"
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query(query, conn)
        conn.close()
        df = df[df['statusApproval'] != 'NeedAction']
        df.to_csv(out_csv, index=False)
        csv_files.append(out_csv)
    except Exception as e:
        print(f"❌ Error with {db_path}: {e}")

if not csv_files:
    print("⚠️ No CSVs generated.")
    exit(1)

# 📊 Aggregate
df_all = pd.concat([pd.read_csv(f) for f in csv_files])
df_all['monitoring_date'] = pd.to_datetime(df_all['monitoring_date'], errors='coerce')
df_all['code'] = df_all['code'].str.replace(r'^MAN-(\d{1})$', r'MAN-00\1', regex=True)
df_all['code'] = df_all['code'].str.replace(r'^MAN-(\d{2})$', r'MAN-0\1', regex=True)
df_all['code'] = df_all['code'].str.replace(r'^MAN', 'JJK', regex=True)
df_latest = df_all.sort_values('monitoring_date').dropna(subset=['code']).drop_duplicates('code', keep='last')

# 🔐 Google Sheets
SERVICE_ACCOUNT_FILE = "credentials.json"
SHEET_NAME = "Mangrove Database"
WORKSHEET_NAME = "TreeStatus"

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly"])

gc = gspread.authorize(creds)
ws = gc.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
data = ws.get_all_values()
df_status = pd.DataFrame(data[1:], columns=data[0]).iloc[:, :2]
df_status.columns = ['code', 'status']

# 🔗 Merge status
df_latest = df_latest.merge(df_status, on="code", how="left")
df_latest["status"] = df_latest["status"].fillna("Unknown")

# 🎨 Marker colors
def get_color_tuple(status):
    s = str(status).strip().lower()
    if s == "dead":
        return ("red", "red")
    elif s == "alive":
        return ("green", "green")
    return ("black", "#ccc")

df_latest[["border_color", "fill_color"]] = df_latest["status"].apply(lambda s: pd.Series(get_color_tuple(s)))
df_latest.to_csv(output_csv, index=False)

# 🗺️ Create map
center_lat = df_latest["latitude"].mean()
center_lon = df_latest["longitude"].mean()
m = folium.Map(location=[center_lat, center_lon], zoom_start=13, control_scale=True, tiles="OpenStreetMap")

folium.TileLayer(
    name="Satellite",
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Tiles © Esri"
).add_to(m)

Fullscreen(position="topright").add_to(m)

# 📍 Markers
code_to_latlon = {}
for _, row in df_latest.iterrows():
    coord = (row["latitude"], row["longitude"])
    code_to_latlon[row["code"]] = coord
    folium.CircleMarker(
        location=coord,
        radius=5,
        color=row["border_color"],
        fill=True,
        fill_color=row["fill_color"],
        fill_opacity=0.9,
        weight=1,
        popup=folium.Popup(
            f"<b>ID:</b> {row['tree_id']}<br>"
            f"<b>Name:</b> {row['tree_name']}<br>"
            f"<b>Code:</b> {row['code']}<br>"
            f"<b>Status:</b> {row['status']}",
            max_width=250
        )
    ).add_to(m)

# 📊 Summary + search
total = len(df_latest)
dead = (df_latest['fill_color'] == 'red').sum()
alive = (df_latest['fill_color'] == 'green').sum()
unknown = (df_latest['fill_color'] == '#ccc').sum()

search_js_dict = ",\n".join([f'"{code}": [{lat}, {lon}]' for code, (lat, lon) in code_to_latlon.items()])
m.get_root().html.add_child(Element(f"""
<div style="position: absolute; bottom: 20px; left: 10px; z-index: 9999;
     background: white; padding: 12px 15px; border-radius: 8px;
     box-shadow: 0 0 5px rgba(0,0,0,0.3); font-family: sans-serif; font-size: 14px;">
<b>Total:</b> {total} |
<span style='color:red'>Dead: {dead}</span> |
<span style='color:green'>Alive: {alive}</span> |
<span style='color:gray'>Unknown: {unknown}</span><br><br>
<input type="text" id="searchBox" placeholder="Search code..."
 style="padding:4px; width:160px;">
</div>
<script>
const codeCoordinates = {{
{search_js_dict}
}};
document.getElementById("searchBox").addEventListener("keypress", function(e) {{
    if (e.key === "Enter") {{
        const code = this.value.trim().toUpperCase();
        const coords = codeCoordinates[code];
        if (coords) {{
            const circle = L.circleMarker(coords, {{
                radius: 12,
                color: 'black',
                fillColor: 'orange',
                fillOpacity: 0.7
            }}).addTo(window.map);
            circle.bindPopup("Code: " + code).openPopup();
            window.map.setView(coords, 18, {{ animate: true }});
        }} else {{
            alert("Code not found.");
        }}
    }}
}});
</script>
"""))

# 🏷️ Legend
m.get_root().html.add_child(Element("""
<div style="
     position: fixed;
     bottom: 200px;
     left: 10px;
     z-index: 9999;
     background-color: white;
     padding: 10px;
     border: 2px solid grey;
     border-radius: 8px;
     box-shadow: 2px 2px 6px rgba(0,0,0,0.3);
     font-family: sans-serif;
     font-size: 14px;
">
<b>Legend</b><br>
<span style="display:inline-block;width:12px;height:12px;background-color:red;margin-right:5px;"></span> Dead<br>
<span style="display:inline-block;width:12px;height:12px;background-color:green;margin-right:5px;"></span> Alive<br>
<span style="display:inline-block;width:12px;height:12px;background-color:#ccc;border:1px solid black;margin-right:5px;"></span> Unknown
</div>
"""))

# 🛠 JS map ref
m.get_root().script.add_child(Element("""
document.addEventListener("DOMContentLoaded", function () {
    const mapId = document.querySelector("div[id^='map_']").id;
    window.map = window[mapId.replace("-", "_")];
});
"""))

# 📥 Download button (CSV + KML)
download_menu = f"""
<div style="position: absolute; top: 10px; left: 10px; z-index: 9999;">
  <details style="background: white; padding: 10px; border-radius: 8px; box-shadow: 1px 1px 5px #aaa;">
    <summary style="cursor: pointer; font-weight: bold;">📥 Downloads</summary>
    <div style="margin-top: 8px; line-height: 1.6;">
      <a href="{output_csv}" download>📄 Download CSV</a><br>
      <a href="{output_kml}" download>🌍 Download KML</a>
    </div>
  </details>
</div>
"""
m.get_root().html.add_child(Element(download_menu))

# 💾 Save map
m.save("tree_map.html")
print("✅ Map saved: tree_map.html")

# 🌐 Export GeoJSON
geojson = {
    "type": "FeatureCollection",
    "features": []
}
for _, row in df_latest.iterrows():
    geojson["features"].append({
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [row["longitude"], row["latitude"]]},
        "properties": {
            "tree_id": row["tree_id"],
            "tree_name": row["tree_name"],
            "code": row["code"],
            "status": row["status"]
        }
    })
with open(output_geojson, "w", encoding="utf-8") as f:
    json.dump(geojson, f, indent=2)

# 🌍 Export KML
kml = simplekml.Kml()
for _, row in df_latest.iterrows():
    kml.newpoint(name=str(row["code"]), description=row["tree_name"], coords=[(row["longitude"], row["latitude"])])
kml.save(output_kml)
print("✅ KML exported.")
