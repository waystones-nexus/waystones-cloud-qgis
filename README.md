# Waystones Cloud QGIS Plugin

[![QGIS Version](https://img.shields.io/badge/QGIS-4.0+-blue.svg)](https://qgis.org)
[![License](https://img.shields.io/badge/License-GPL--2.0--or--later-green.svg)](LICENSE)

Publish, host, and manage vector datasets from QGIS directly to [Waystones Cloud](https://waystones.cloud) with a single click. Instantly deploy scalable **OGC API Features (OAPIF)**, **Vector Tiles**, and **STAC Catalogs** without managing servers, configuration files, or database connections.

---

## Key Features

*   📦 **Native Multi-Layer Bundling** – Select any combination of open vector layers (Shapefiles, GeoJSON, PostGIS, GPKG, GML, KML, etc.). The plugin packs them into a single GeoPackage automatically.
*   🎛 **Dedicated "Projects" Panel** – Manage your cloud deployments right inside QGIS. View, edit metadata, change deployed services, manage API keys, and delete projects safely.
*   📐 **Vector Tiles & STAC on Demand** – Turn on tile services with automatic zoom-range detection (based on layer extents) or manual overrides. Generate structured STAC catalogs partitioned by attribute columns.
*   🔒 **Fine-grained Access Controls** – Deploy public endpoints or lock down datasets as private. Generate, label, and revoke project-specific API keys from the sidebar panel.
*   🌐 **Corporate Proxy Compliance** – Built entirely on QGIS's native `QgsNetworkAccessManager`, ensuring network requests respect your system's proxy settings, authentication configurations, and SSL certificates.
*   🖌 **Style Fidelity Preservation** – Automatically carries over your QGIS symbology (single symbol, categorized colors, simple fills/lines, point icons, and labels) directly to the cloud.

---

## Installation

### From ZIP (Easiest)
1. Download the latest release `.zip` archive from the [Releases Page](https://github.com/waystones-nexus/waystones-cloud-qgis/releases).
2. Open QGIS and navigate to **Plugins** ➔ **Manage and Install Plugins** ➔ **Install from ZIP**.
3. Browse to the downloaded `.zip` file and click **Install Plugin**.

### From Source (Development & Debugging)
To install the plugin directly from source, copy or symlink the folder into your local QGIS plugins directory:

```bash
# Windows (PowerShell)
xcopy /E /I waystones-cloud-qgis "$env:APPDATA\QGIS\QGIS3\profiles\default\python\plugins\waystones_cloud"

# macOS & Linux
cp -r waystones-cloud-qgis ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/waystones_cloud
```
Then, enable the plugin in QGIS under **Plugins** ➔ **Manage and Install Plugins** ➔ **Installed**.

---

## How It Works

```text
Select QGIS Layers ───> Auto-package (GPKG) ───> Upload (QgsNetworkAccessManager) ───> Waystones Cloud ───> Live Endpoints (OAPIF/Tiles/STAC)
```

---

## Detailed Usage Guide

### 1. Set Up Your Account
*   Navigate to the **Account** tab in the sidebar.
*   Paste your API Key (generate one on [waystones.cloud/api](https://waystones.cloud/api)). The key will be securely saved locally.
*   *Bonus: Enjoy the companion units waiting at the bottom of the tab to help guide your deployment!*

### 2. Configure Your Source & Scope
*   Under the **Source** tab, check the vector layers you want to publish.
*   Enter a **Project Name** and a custom **URL Slug**.
*   Select whether the project should be **Private** (requires authorization) or pinned to a specific jurisdiction like the **EU** (GDPR compliant).

### 3. Polish Metadata & Symbology
*   Fill in contact details, keywords, licensing information, and access restrictions in the **Metadata** tab.
*   Use **Auto-detect from checked layers** to calculate the spatial extent bounding box automatically.
*   Switch to the **Layers** tab to define user-friendly layer titles, descriptions, and customize how the style will translate to the cloud.

### 4. Select Services & Deploy
*   In the **Services** tab, select which cloud configurations you want:
    *   **OGC API Features (OAPIF)** – Clean, JSON-based feature querying.
    *   **Vector Tiles** – Blazing fast rendering. Choose *Auto-detect zoom range* or configure custom min/max zooms and geometry simplification.
    *   **STAC Catalog** – Flat catalog or partitioned hierarchically by custom attribute columns.
*   Click **Deploy** in the bottom bar and watch the real-time provisioning logs.

---

## Managing Existing Projects

Open the **Projects** tab in the sidebar to review and manage already-live datasets:

*   **Endpoint Hub**: View public/private URLs, web-based visualizers, and raw API links. Copy tile style URLs or STAC configurations directly into QGIS or your custom map application.
*   **Update Files**: Click **Replace GPKG...** to swap out the underlying GeoPackage file with updated layers while keeping the existing endpoints, slug, and settings intact.
*   **Regenerate Services**: Manually re-run vector tile or STAC catalog generation with updated options.
*   **Key Manager**: Create, label, copy, or revoke API access keys for your private deployments.
*   **Metadata & Services**: Adjust metadata fields or add/remove services without redeploying from scratch.

---

## Development & Contribution

We welcome issues, feedback, and pull requests! Feel free to open an issue on the [GitHub Tracker](https://github.com/waystones-nexus/waystones-cloud-qgis/issues).
