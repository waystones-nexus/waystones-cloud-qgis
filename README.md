# Waystones Cloud QGIS Plugin

Publish any vector layer open in QGIS directly to [Waystones Cloud](https://waystones.cloud) — OAPIF, vector tiles, and STAC with one click.

## What it does

1. Exports the selected QGIS layer to GeoPackage (any format QGIS can open works — shapefiles, GeoJSON, PostGIS, KML, etc.)
2. Uploads the GPKG to Waystones Cloud
3. Creates a project and deploys it with the slug and services you chose
4. Streams the provisioning log in real time until the endpoint is live

## Requirements

- QGIS 4.0 or later (uses bundled Python + `requests`)
- A [Waystones Cloud](https://waystones.cloud) account and API key

## Installation

**From ZIP (easiest):**

1. Download the latest release ZIP from the [releases page](https://github.com/waystones-nexus/waystones-cloud-qgis/releases)
2. In QGIS: *Plugins → Manage and Install Plugins → Install from ZIP*
3. Browse to the downloaded ZIP and click **Install Plugin**

**From source (development):**

```
# Windows
xcopy /E /I waystones-cloud-qgis "%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\waystones_cloud"

# macOS / Linux
cp -r waystones-cloud-qgis ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/waystones_cloud
```

Then enable the plugin in *Plugins → Manage and Install Plugins → Installed*.

## Usage

1. Open the tool via *Web → Waystones Cloud → Publish to Waystones Cloud* or the toolbar button
2. Paste your API key (saved automatically after first use)
3. Select a vector layer from the dropdown
4. Set a project name and slug
5. Check which services to deploy — any combination of OAPIF, vector tiles, and STAC works
6. Click **Deploy** and watch the log

## Multi-layer projects

To publish multiple layers as one project, merge them into a single GeoPackage manually and open it in QGIS first, or use QGIS's *Package Layers* tool (*Processing → Vector General → Package Layers*) to bundle them, then select any layer from that GPKG.
