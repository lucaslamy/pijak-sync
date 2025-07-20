import sqlite3
import pandas as pd
import folium
import base64
import re
from folium.plugins import Fullscreen, Search
from folium import Element
from folium.plugins import HeatMap
from folium import IFrame
from folium.plugins import FeatureGroupSubGroup
import simplekml
import json
import os
from glob import glob
import gspread
from google.oauth2.service_account import Credentials
from branca.element import MacroElement
from jinja2 import Template
from PIL import Image, ExifTags
from PIL.ExifTags import TAGS, GPSTAGS
import subprocess
import urllib.request

# Var 
# FOR PRODUCTION : TRUE IF YOU HAVE THUMBNAILS, FALSE IF LOCAL DEV : 
isThumbnailsEnabled = False

# 🔧 Output paths
output_csv = "geotagged_tree_aggregated_latest.csv"
output_geojson = "geotagged_tree.geojson"
output_kml = "geotagged_tree.kml"
output_geojson_pijak = "pijak_tree.geojson"
output_kml_pijak = "pijak_tree.kml"

# 📁 Folder with .db files
db_folder = './db'
csv_files = []

pictures_folder = "pictures"
pijak_pictures_folder = "pijak_foto"
image_markers = folium.FeatureGroup(name="Photos EXIF", show=False)

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

class AssignMapToWindow(MacroElement):
    def __init__(self):
        super().__init__()
        self._template = Template("""
            {% macro script(this, kwargs) %}
                window.map = {{this._parent.get_name()}};
            {% endmacro %}
        """)
        
# 🎨 Marker colors
def get_color_tuple(status):
    s = str(status).strip().lower()
    if s == "dead": return ("red", "red")
    elif s == "alive": return ("green", "green")
    return ("black", "#ccc")
    
def remap_kode(k):
    match = re.match(r"MAN-(\d+)", str(k).strip().upper())
    if match:
        num = int(match.group(1))
        return f"JJK-{num:03d}"
    return k 

def dms_to_decimal(dms_str):
    if not isinstance(dms_str, str):
        raise ValueError(f"Coordonnée DMS invalide : {dms_str}")
    
    dms_regex = r"(\d+)\D+(\d+)\D+([\d.]+)\D+([NSEW])"
    match = re.match(dms_regex, dms_str)
    if not match:
        raise ValueError(f"Format DMS non reconnu : {dms_str}")
    
    degrees, minutes, seconds, direction = match.groups()
    decimal = float(degrees) + float(minutes) / 60 + float(seconds) / 3600
    if direction in ['S', 'W']:
        decimal *= -1
    return decimal

def extract_gps_from_images(folder="pictures"):
    cmd = [
        "exiftool",
        "-gpslatitude",
        "-gpslongitude",
        "-filename",
        "-json",
        folder
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError("ExifTool error: " + result.stderr)
    
    data = json.loads(result.stdout)
    image_points = []
    for item in data:
        if not item.get('GPSLatitude') or not item.get('GPSLongitude'):
            continue

        lat = dms_to_decimal(item.get('GPSLatitude'))
        lon = dms_to_decimal(item.get('GPSLongitude'))
        filename = item.get("SourceFile")
        if lat and lon:
            image_points.append((lat, lon, os.path.basename(filename)))
    return image_points

def add_image_markers(map_object, image_points, group_name="Photos"):
    feature_group = folium.FeatureGroup(name=group_name, show=False)

    for lat, lon, file_path in image_points:
        try:
            if isThumbnailsEnabled:
                # FOR PRODUCTION WHEN YOU HAVE THUMBNAILS : 
                img_path = 'pictures/thumbnails/tn_' + file_path
            else:
                # FOR LOCAL DEV : 
                img_path = pictures_folder + '/' + file_path

            full_res_img_path = pictures_folder + '/' + file_path

            if not os.path.exists(img_path) and not isThumbnailsEnabled :
                print(f"⚠️ File not found: {img_path}")
                continue

            popup_html = f'''
            <a href="{full_res_img_path}" target="_blank">
                <img data-src="{img_path}" 
                    src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==" 
                    style="max-width:600px; max-height:400px; display:block;"                         class="lazy-image">
            </a>
            '''
            popup = folium.Popup(popup_html, width=400, max_height=500)

            folium.Marker(
                location=[lat, lon],
                popup=popup,
                icon=folium.Icon(color="blue", icon="camera", prefix="fa")
            ).add_to(feature_group)

        except Exception as e:
            print(f"❌ Could not load image {img_path}: {e}")
    
    feature_group.add_to(map_object)


def get_pijak_colors(status):
    s = str(status).strip().lower()
    if s == 'dead': return ('#990000', '#ff9999')
    elif s == 'alive': return ('#006600', '#66ff66')
    return ('#666666', '#cccccc')


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
df_latest[["border_color", "fill_color"]] = df_latest["status"].apply(lambda s: pd.Series(get_color_tuple(s)))
df_latest.to_csv(output_csv, index=False)

# 📚 Load Pijak DB
df_pijak = pd.DataFrame(gc.open(SHEET_NAME).worksheet("Pijak DB").get_all_records())
df_pijak = df_pijak[df_pijak['Status'].str.lower().str.strip().str.contains("geotag")]
df_pijak['Latitude'] = pd.to_numeric(df_pijak['Latitude'], errors='coerce')
df_pijak['Longitude'] = pd.to_numeric(df_pijak['Longitude'], errors='coerce')
df_pijak = df_pijak.dropna(subset=['Latitude', 'Longitude'])
df_pijak['Kode'] = df_pijak['Kode'].apply(remap_kode)
df_pijak[["border_color", "fill_color"]] = df_pijak["Tree Status"].apply(lambda s: pd.Series(get_pijak_colors(s)))

# 🌍 Create map
center_lat = df_latest["latitude"].mean()
center_lon = df_latest["longitude"].mean()
m = folium.Map(location=[center_lat, center_lon], zoom_start=16, control_scale=True, tiles="OpenStreetMap")

favicon = Element('''
<link rel="icon" href="favicon.ico" type="image/x-icon">
''')
m.get_root().html.add_child(favicon)

title = Element('''
<title>🌱 Mangrove Project</title>
''')
m.get_root().html.add_child(title)

m.add_child(AssignMapToWindow())
folium.TileLayer(
    name="Satellite",
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Tiles © Esri"
).add_to(m)
Fullscreen(position="topright").add_to(m)

# 📍 Markers
tree_layer = folium.FeatureGroup(name="Previous DB", show=False)
marker_dict = {}
for _, row in df_latest.iterrows():
    coord = (row["latitude"], row["longitude"])
    marker = folium.CircleMarker(
        location=coord,
        radius=5,
        color=row["border_color"],
        fill=True,
        fill_color=row["fill_color"],
        fill_opacity=0.9,
        weight=1,
        popup=folium.Popup(
            f"<b>ID:</b> {row['tree_id']}<br>"
            f"<b>Code:</b> {row['code']}<br>"
            f"<b>Status:</b> {row['status']}",
            max_width=250
        ),
        tooltip=row["code"]
    )
    marker.add_to(tree_layer)
    marker_dict[row['code']] = marker
tree_layer.add_to(m)

# 🌳 Current DB layer
pijak_layer = folium.FeatureGroup(name="Current DB")
missing_images = []

for _, row in df_pijak.iterrows():
    html = f"<b>Kode:</b> {row['Kode']}<br><b>Status:</b> {row['Tree Status']}"
    foto_path = row.get("Foto 1")
    img_tag = "<br><em>Picture not available</em>"

    if foto_path:
        local_filename = os.path.basename(foto_path)
        local_path = os.path.join(pijak_pictures_folder, local_filename)
        
        # Téléchargement si image manquante localement
        if not os.path.isfile(local_path):
            try:
                print(f"⬇️ Downloading missing image for {row['Kode']} from {foto_path}...")
                urllib.request.urlretrieve(foto_path, local_path)
                print(f"✅ Image saved to {local_path}")
            except Exception as e:
                print(f"❌ Failed to download image for {row['Kode']}: {e}")
        
        if isThumbnailsEnabled:
            # FOR PRODUCTION WHEN YOU HAVE THUMBNAILS : 
            thumbnail_path = f"pijak_foto/thumbnails/tn_{local_filename}"
        else:
            # FOR LOCAL DEV : 
            thumbnail_path = local_path

        # Si l'image est bien présente localement ou a été téléchargée
        if os.path.isfile(local_path):
            # Utilisation d’un placeholder transparent et lazy-loading
            img_tag = f"""
            <br><a href="{foto_path}" target="_blank">
                <img data-src="{thumbnail_path}" 
                     src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==" 
                     width="150"
                     class="lazy-image"
                >
            </a>
            """
        else:
            missing_images.append(foto_path)
            img_tag = f"""
            <br><a href="{foto_path}" target="_blank">
                <img data-src="{thumbnail_path}" 
                     src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==" 
                     width="150"
                     class="lazy-image"
                >
            </a>
            """

    html += img_tag

    folium.CircleMarker(
        location=(row["Latitude"], row["Longitude"]),
        radius=6,
        color=row['border_color'],
        fill=True,
        fill_color=row['fill_color'],
        fill_opacity=0.85,
        weight=1.5,
        popup=folium.Popup(html, max_width=250),
        tooltip=row["Kode"]
    ).add_to(pijak_layer)

if missing_images:
    print("🚫 Missing local images :", missing_images)

pijak_layer.add_to(m)


image_points = extract_gps_from_images(pictures_folder)
add_image_markers(m, image_points, group_name="Geotagged Photos")

df_pijak['Lat_bin'] = (df_pijak['Latitude'] * 10000).round() / 10000
df_pijak['Lon_bin'] = (df_pijak['Longitude'] * 10000).round() / 10000

zone_stats = df_pijak.groupby(['Lat_bin', 'Lon_bin']).agg(
    Mort=('Tree Status', lambda x: (x == 'Dead').sum()),
    Vivant=('Tree Status', lambda x: (x == 'Alive').sum()),
    Latitude=('Latitude', 'mean'),
    Longitude=('Longitude', 'mean')
).reset_index()

zone_stats['ratio'] = zone_stats['Mort'] / zone_stats['Vivant'].replace(0, 1)

max_ratio = 10.0
zone_stats['ratio_norm'] = zone_stats['ratio'].clip(upper=max_ratio) / max_ratio
zone_stats = zone_stats[(zone_stats['Mort'] + zone_stats['Vivant']) >= 3]


heat_data = [
    [row['Latitude'], row['Longitude'], min(row['ratio_norm'] * 1.2, 1.0)]
    for _, row in zone_stats.iterrows()
]

gradient = {
    0.0: 'transparent',  
    0.25: 'darkgreen',   
    0.5: 'yellowgreen',  
    0.7: 'orange',
    0.85: 'orangered',
    1.0: 'red'            
}


HeatMap(
    heat_data,
    min_opacity=0.6,      
    radius=12,          
    blur=4,               
    max_zoom=18,
    gradient=gradient,
    name="Heatmap (Dead/Alive Ratio)"
).add_to(m)


# Fix window.map
fix_map_js = """
<script>
document.addEventListener("DOMContentLoaded", function() {
    const mapDiv = document.querySelector("div[id^='map_']");
    if (mapDiv && mapDiv._leaflet_map) {
        window.map = mapDiv._leaflet_map;
    }
});
</script>
"""
m.get_root().html.add_child(Element(fix_map_js))

# 🧭 Layer + Legend
total = len(df_pijak)
dead = (df_pijak['Tree Status'] == 'Dead').sum()
alive = (df_pijak['Tree Status'] == 'Alive').sum()
total_pct = f"{total/4103:.2%}"
dead_pct = f"{dead/total:.2%}"
alive_pct = f"{alive/total:.2%}"

folium.LayerControl(collapsed=False).add_to(m)

m.get_root().html.add_child(Element(f"""
<div style="position: fixed; bottom: 120px; left: 10px; z-index: 9999; background-color: white; padding: 10px; border: 2px solid grey; border-radius: 8px; font-size: 14px;">
<b>Legend</b><br>
<b>Total geo-tagged with Pijak:</b> {total}/4103 ({total_pct})<br>
<span style='background-color:#ff9999;width:12px;height:12px;display:inline-block;margin-right:5px;'></span> Dead: {dead} ({dead_pct})<br>
<span style='background-color:#66ff66;width:12px;height:12px;display:inline-block;margin-right:5px;'></span> Alive: {alive} ({alive_pct})<br>
</div>
"""))


# 📥 Download button (CSV + KML)
download_menu = f"""
<div style="position: absolute; top: 10px; left: 10px; z-index: 9999;">
  <details style="background: white; padding: 10px; border-radius: 8px; box-shadow: 1px 1px 5px #aaa;">
    <summary style="cursor: pointer; font-weight: bold;">📥 Downloads</summary>
    <div style="margin-top: 8px; line-height: 1.6;">
      <a href="{output_csv}" download>📄 Download CSV</a><br>
      <a href="{output_geojson}" download>🌍 Download Local GeoJSON</a><br>
      <a href="{output_kml}" download>🌍 Download Local KML</a><br>
      <a href="{output_geojson_pijak}" download>🌍 Download Pijak GeoJSON</a><br>
      <a href="{output_kml_pijak}" download>🌍 Download Pijak KML</a>
    </div>
  </details>
</div>
"""
m.get_root().html.add_child(Element(download_menu))

search_html = """
<style>
    #searchContainer {
        position: fixed;
        bottom: 60px;
        left: 10px;
        z-index: 9999;
        background-color: white;
        padding: 8px 12px;
        border-radius: 8px;
        box-shadow: 0 0 8px rgba(0,0,0,0.3);
        font-family: sans-serif;
        width: 220px;
    }
    #searchInput {
        width: 100%;
        padding: 5px;
        font-size: 14px;
        border: 1px solid #ccc;
        border-radius: 4px;
    }
    #autocompleteList {
        position: absolute;
        top: 38px;
        left: 10px;
        background-color: white;
        border: 1px solid #ccc;
        border-top: none;
        max-height: 180px;
        overflow-y: auto;
        width: 220px;
        z-index: 99999;
        display: none;
    }
    .autocompleteItem {
        padding: 6px 10px;
        cursor: pointer;
    }
    .autocompleteItem:hover {
        background-color: #f0f0f0;
    }
</style>

<div id="searchContainer">
    <input type="text" id="searchInput" placeholder="🔍 Search code..." autocomplete="off"/>
    <div id="autocompleteList"></div>
</div>

<script>
document.addEventListener("DOMContentLoaded", function () {
    window.markersByStatus = {
        "alive": [],
        "dead": [],
        "unknown": []
    };

    Object.values(window.map._layers).forEach(layer => {
        if (layer instanceof L.CircleMarker && layer.options && layer.options.fillColor) {
            const fillColor = layer.options.fillColor.toLowerCase();
            if (fillColor === "#66ff66") {
                window.markersByStatus.alive.push(layer);
            } else if (fillColor === "#ff9999") {
                window.markersByStatus.dead.push(layer);
            } else {
                window.markersByStatus.unknown.push(layer);
            }
        }
    });

    const codeToLayer = {};

    // Scan tous les layers pour extraire les codes des tooltips
    Object.values(window.map._layers).forEach(layer => {
        if (layer.getTooltip && layer.getTooltip()) {
            let raw = layer.getTooltip()._content;
            if (raw) {
                // Nettoie le code (strip balises HTML, trim, minuscule)
                const clean = raw.replace(/<[^>]+>/g, '').trim();
                if (clean) {
                    codeToLayer[clean] = layer;
                }
            }
        }
    });

    const input = document.getElementById('searchInput');
    const list = document.getElementById('autocompleteList');
    const codeList = Object.keys(codeToLayer);

    input.addEventListener('input', function () {
        const query = this.value;
        list.innerHTML = '';
        if (!query) {
            list.style.display = 'none';
            return;
        }

        const matches = codeList.filter(c => c.includes(query));
        matches.slice(0, 20).forEach(match => {
            const item = document.createElement('div');
            item.className = 'autocompleteItem';
            item.textContent = match;
            item.onclick = function () {
                input.value = match;
                list.style.display = 'none';

                const layer = codeToLayer[match];
                if (layer) {
                    const latlng = layer.getLatLng();
                    window.map.setView(latlng, 19);
                    layer.openPopup();
                }
            };
            list.appendChild(item);
        });

        list.style.display = matches.length > 0 ? 'block' : 'none';
    });

    document.addEventListener('click', function (e) {
        if (!document.getElementById('searchContainer').contains(e.target)) {
            list.style.display = 'none';
        }
    });
});
</script>

"""

m.get_root().html.add_child(folium.Element(search_html))

fix_map_js = """
<script>
document.addEventListener("DOMContentLoaded", function() {
    const mapDiv = document.querySelector("div[id^='map_']");
    if (mapDiv && mapDiv._leaflet_map) {
        window.map = mapDiv._leaflet_map;
    }
});
</script>
"""
m.get_root().html.add_child(Element(fix_map_js))

status_filter_html = """
<div style="position: fixed; top: 187px; left: 10px; z-index: 9999; background: white; padding: 10px;
    border-radius: 8px; border: 1px solid #aaa; font-family: sans-serif; box-shadow: 2px 2px 6px rgba(0,0,0,0.2);">
    <b>🧪 Filter Status</b><br>
    <label><input type="radio" name="statusFilter" value="all" checked> All</label><br>
    <label><input type="radio" name="statusFilter" value="alive"> Alive</label><br>
    <label><input type="radio" name="statusFilter" value="dead"> Dead</label><br>
</div>

<script>
document.addEventListener("DOMContentLoaded", function () {
    const radios = document.querySelectorAll('input[name="statusFilter"]');

    function updateVisibility(status) {
        for (const s in window.markersByStatus) {
            window.markersByStatus[s].forEach(marker => {
                if (status === "all" || s === status) {
                    marker.setStyle({ opacity: 1, fillOpacity: 0.85 });
                } else {
                    marker.setStyle({ opacity: 0, fillOpacity: 0 });
                }
            });
        }
    }

    radios.forEach(radio => {
        radio.addEventListener("change", function () {
            updateVisibility(this.value);
        });
    });
});
</script>
"""
m.get_root().html.add_child(Element(status_filter_html))

legend_html = """
{% macro html(this, kwargs) %}

<div style="
    position: fixed; 
    bottom: 45px;
    right: 45px;
    width: 240px;
    height: auto;
    z-index:9999;
    background-color: white;
    border:2px solid grey;
    border-radius:8px;
    padding: 12px;
    font-size: 14px;
    box-shadow: 2px 2px 5px rgba(0,0,0,0.3);
">
    <b>Dead / Alive Tree Ratio</b><br>
    <i>(normalized, max = 10:1)</i><br><br>
    <div><span style="background-color: darkgreen; width: 20px; height: 12px; display: inline-block;"></span> &nbsp;Low mortality (≤ 2.5:1)</div>
    <div><span style="background-color: yellowgreen; width: 20px; height: 12px; display: inline-block;"></span> &nbsp;Moderate (2.5:1 – 5:1)</div>
    <div><span style="background-color: orange; width: 20px; height: 12px; display: inline-block;"></span> &nbsp;High (5:1 – 7:1)</div>
    <div><span style="background-color: orangered; width: 20px; height: 12px; display: inline-block;"></span> &nbsp;Very high (7:1 – 8.5:1)</div>
    <div><span style="background-color: red; width: 20px; height: 12px; display: inline-block;"></span> &nbsp;Extreme (≥ 8.5:1)</div>
</div>

{% endmacro %}
"""

lazy_load_script = """
<script>
document.addEventListener("DOMContentLoaded", function () {
    window.map.on('popupopen', function (e) {
        var popup = e.popup;
        var imgs = popup._contentNode.querySelectorAll("img.lazy-image");
        imgs.forEach(function (img) {
            if (img.dataset.src) {
                img.src = img.dataset.src;
                img.removeAttribute("data-src");
            }
        });
    });
});
</script>
"""
m.get_root().html.add_child(folium.Element(lazy_load_script))

legend = MacroElement()
legend._template = Template(legend_html)
m.get_root().add_child(legend)

m.save("tree_map.html")

with open("tree_map.html", "r", encoding="utf-8") as f:
    html = f.read()

html = re.sub(r'^\s*window\.map\s*=\s*element_[a-f0-9]+;\s*$', '', html, flags=re.MULTILINE)

if not html.lstrip().lower().startswith("<!doctype html>"):
    html = "<!DOCTYPE html>\n" + html

# 💾 Save map
m.save("tree_map.html")
print("✅ Map saved: tree_map.html")

# 🌐 Export GEOJSON Combined
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
            "status": row["status"],
            "source": "DB"
        }
    })
for _, row in df_pijak.iterrows():
    geojson["features"].append({
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [row["Longitude"], row["Latitude"]]},
        "properties": {
            "tree_name": row["Nama pohon"],
            "code": row["Kode"],
            "status": row["Tree Status"],
            "source": "PIJAK"
        }
    })
with open(output_geojson, "w", encoding="utf-8") as f:
    json.dump(geojson, f, indent=2)

# 🌐 Export GEOJSON Pijak Only
geojson_pijak = {
    "type": "FeatureCollection",
    "features": []
}
for _, row in df_pijak.iterrows():
    geojson_pijak["features"].append({
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [row["Longitude"], row["Latitude"]]},
        "properties": {
            "tree_name": row["Nama pohon"],
            "code": row["Kode"],
            "status": row["Tree Status"]
        }
    })
with open(output_geojson_pijak, "w", encoding="utf-8") as f:
    json.dump(geojson_pijak, f, indent=2)

# 🌍 Export KML Combined
kml = simplekml.Kml()
for _, row in df_latest.iterrows():
    kml.newpoint(name=str(row["code"]), description=f"[DB] {row['tree_name']}", coords=[(row["longitude"], row["latitude"])])
for _, row in df_pijak.iterrows():
    kml.newpoint(name=str(row["Kode"]), description=f"[PIJAK] {row['Nama pohon']}", coords=[(row["Longitude"], row["Latitude"])])
kml.save(output_kml)

# 🌍 Export KML Pijak Only
kml_pijak = simplekml.Kml()
for _, row in df_pijak.iterrows():
    kml_pijak.newpoint(name=str(row["Kode"]), description=row["Nama pohon"], coords=[(row["Longitude"], row["Latitude"])])
kml_pijak.save(output_kml_pijak)

print("✅ Map and exports generated.")