import os
import re
import tempfile
import threading

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QScrollArea, QWidget,
    QLineEdit, QPushButton, QCheckBox, QComboBox,
    QTextEdit, QProgressBar, QGroupBox, QSpinBox, QLabel,
    QMessageBox, QTabWidget, QDoubleSpinBox,
)
from qgis.PyQt.QtCore import QSettings, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QFont, QColor
from qgis.gui import QgsMapLayerComboBox, QgsColorButton
from qgis.core import (
    QgsMapLayerProxyModel, QgsVectorFileWriter, QgsProject,
    QgsWkbTypes, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
)

from .api import WaystonesAPI, WaystonesAPIError

SETTINGS_KEY_API_KEY = "waystones_cloud/api_key"
SETTINGS_KEY_DATA_REGION = "waystones_cloud/data_region"
SETTINGS_KEY_IS_PRIVATE = "waystones_cloud/is_private"
POLL_INTERVAL_MS = 5000
DEFAULT_COLOR = "#4A90D9"


class WaystonesDialog(QDialog):
    _log_line = pyqtSignal(str)
    _progress = pyqtSignal(int, int)
    _deploy_done = pyqtSignal(str)
    _deploy_error = pyqtSignal(str)

    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.setWindowTitle("Publish to Waystones Cloud")
        self.setMinimumWidth(540)
        self._deployment_id = None
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_deployment)
        self._poll_log_offset = 0
        self._build_ui()
        self._connect_signals()
        self._load_settings()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        tabs = QTabWidget()
        tabs.addTab(self._build_account_tab(), "Account")
        tabs.addTab(self._build_dataset_tab(), "Dataset")
        tabs.addTab(self._build_metadata_tab(), "Metadata")
        tabs.addTab(self._build_style_tab(), "Style")
        tabs.addTab(self._build_services_tab(), "Services")
        root.addWidget(tabs)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        root.addWidget(self._progress_bar)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(120)
        mono = QFont("Courier New", 9)
        mono.setStyleHint(QFont.Monospace)
        self._log.setFont(mono)
        root.addWidget(self._log)

        btn_row = QHBoxLayout()
        self._deploy_btn = QPushButton("Deploy")
        self._deploy_btn.setDefault(True)
        self._close_btn = QPushButton("Close")
        btn_row.addStretch()
        btn_row.addWidget(self._close_btn)
        btn_row.addWidget(self._deploy_btn)
        root.addLayout(btn_row)

    def _build_account_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(12, 12, 12, 12)

        self._api_key_edit = QLineEdit()
        self._api_key_edit.setEchoMode(QLineEdit.Password)
        self._api_key_edit.setPlaceholderText("wsk_…")
        form.addRow("API key:", self._api_key_edit)

        note = QLabel('Get your API key at <a href="https://waystones.cloud">waystones.cloud</a>')
        note.setOpenExternalLinks(True)
        form.addRow(note)

        return w

    def _build_dataset_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(12, 12, 12, 12)

        self._layer_combo = QgsMapLayerComboBox()
        self._layer_combo.setFilters(QgsMapLayerProxyModel.VectorLayer)
        form.addRow("Layer:", self._layer_combo)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("My dataset")
        form.addRow("Name:", self._name_edit)

        self._slug_edit = QLineEdit()
        self._slug_edit.setPlaceholderText("my-dataset")
        form.addRow("Slug:", self._slug_edit)

        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("Brief description of this dataset…")
        self._desc_edit.setMaximumHeight(70)
        form.addRow("Description:", self._desc_edit)

        self._chk_private = QCheckBox("Private (requires authentication to access)")
        form.addRow(self._chk_private)

        self._chk_eu = QCheckBox("Store data in EU (Cloudflare EU jurisdiction)")
        form.addRow(self._chk_eu)

        return w

    def _build_metadata_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(12, 12, 12, 12)

        self._meta_contact_name = QLineEdit()
        form.addRow("Contact name:", self._meta_contact_name)

        self._meta_contact_email = QLineEdit()
        self._meta_contact_email.setPlaceholderText("email@example.com")
        form.addRow("Contact email:", self._meta_contact_email)

        self._meta_contact_org = QLineEdit()
        form.addRow("Organization:", self._meta_contact_org)

        self._meta_keywords = QLineEdit()
        self._meta_keywords.setPlaceholderText("keyword1, keyword2, …")
        form.addRow("Keywords:", self._meta_keywords)

        self._meta_theme = QLineEdit()
        form.addRow("Theme:", self._meta_theme)

        self._meta_license = QLineEdit()
        self._meta_license.setPlaceholderText("e.g. CC BY 4.0")
        form.addRow("License:", self._meta_license)

        self._meta_access_rights = QLineEdit()
        self._meta_access_rights.setPlaceholderText("e.g. Public")
        form.addRow("Access rights:", self._meta_access_rights)

        self._meta_purpose = QTextEdit()
        self._meta_purpose.setPlaceholderText("Purpose / intended use of this dataset…")
        self._meta_purpose.setMaximumHeight(70)
        form.addRow("Purpose:", self._meta_purpose)

        self._meta_periodicity = QLineEdit()
        self._meta_periodicity.setPlaceholderText("e.g. Annual, Monthly, Irregular")
        form.addRow("Update frequency:", self._meta_periodicity)

        self._meta_temporal_from = QLineEdit()
        self._meta_temporal_from.setPlaceholderText("YYYY-MM-DD")
        form.addRow("Temporal from:", self._meta_temporal_from)

        self._meta_temporal_to = QLineEdit()
        self._meta_temporal_to.setPlaceholderText("YYYY-MM-DD")
        form.addRow("Temporal to:", self._meta_temporal_to)

        self._meta_url = QLineEdit()
        self._meta_url.setPlaceholderText("https://…")
        form.addRow("Dataset URL:", self._meta_url)

        self._meta_terms = QLineEdit()
        self._meta_terms.setPlaceholderText("https://…")
        form.addRow("Terms of service:", self._meta_terms)

        form.addRow(QLabel("Spatial extent (WGS 84):"))

        bbox_row1 = QHBoxLayout()
        self._bbox_west = QDoubleSpinBox()
        self._bbox_west.setRange(-180, 180)
        self._bbox_west.setDecimals(6)
        self._bbox_west.setPrefix("W ")
        self._bbox_east = QDoubleSpinBox()
        self._bbox_east.setRange(-180, 180)
        self._bbox_east.setDecimals(6)
        self._bbox_east.setPrefix("E ")
        bbox_row1.addWidget(self._bbox_west)
        bbox_row1.addWidget(self._bbox_east)
        form.addRow(bbox_row1)

        bbox_row2 = QHBoxLayout()
        self._bbox_south = QDoubleSpinBox()
        self._bbox_south.setRange(-90, 90)
        self._bbox_south.setDecimals(6)
        self._bbox_south.setPrefix("S ")
        self._bbox_north = QDoubleSpinBox()
        self._bbox_north.setRange(-90, 90)
        self._bbox_north.setDecimals(6)
        self._bbox_north.setPrefix("N ")
        bbox_row2.addWidget(self._bbox_south)
        bbox_row2.addWidget(self._bbox_north)
        form.addRow(bbox_row2)

        self._bbox_detect_btn = QPushButton("Auto-detect from layer")
        form.addRow(self._bbox_detect_btn)

        scroll.setWidget(w)
        return scroll

    def _build_style_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(12, 12, 12, 12)

        self._color_btn = QgsColorButton()
        self._color_btn.setColor(QColor(DEFAULT_COLOR))
        self._color_btn.setShowNoColor(False)
        form.addRow("Layer color:", self._color_btn)

        note = QLabel("Color used for this layer in the web map viewer.")
        note.setWordWrap(True)
        form.addRow(note)

        self._style_detect_btn = QPushButton("Detect color from current QGIS style")
        form.addRow(self._style_detect_btn)

        return w

    def _build_services_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # OAPIF
        self._chk_oapif = QCheckBox("OGC API Features (OAPIF)")
        self._chk_oapif.setChecked(True)
        layout.addWidget(self._chk_oapif)

        # Vector tiles
        self._chk_tiles = QCheckBox("Vector tiles")
        layout.addWidget(self._chk_tiles)

        self._tiles_options = QGroupBox()
        self._tiles_options.setFlat(True)
        tiles_form = QFormLayout(self._tiles_options)
        tiles_form.setContentsMargins(16, 0, 0, 0)

        self._chk_auto_zoom = QCheckBox("Auto zoom (recommended)")
        self._chk_auto_zoom.setChecked(True)
        tiles_form.addRow(self._chk_auto_zoom)

        zoom_row = QHBoxLayout()
        self._spin_min_zoom = QSpinBox()
        self._spin_min_zoom.setRange(0, 14)
        self._spin_min_zoom.setValue(0)
        self._spin_min_zoom.setEnabled(False)
        self._spin_max_zoom = QSpinBox()
        self._spin_max_zoom.setRange(0, 14)
        self._spin_max_zoom.setValue(14)
        self._spin_max_zoom.setEnabled(False)
        zoom_row.addWidget(QLabel("Min:"))
        zoom_row.addWidget(self._spin_min_zoom)
        zoom_row.addSpacing(12)
        zoom_row.addWidget(QLabel("Max:"))
        zoom_row.addWidget(self._spin_max_zoom)
        zoom_row.addStretch()
        tiles_form.addRow(zoom_row)

        self._chk_custom_simplification = QCheckBox("Custom simplification tolerance")
        tiles_form.addRow(self._chk_custom_simplification)
        self._spin_simplification = QDoubleSpinBox()
        self._spin_simplification.setRange(0.0, 100.0)
        self._spin_simplification.setDecimals(2)
        self._spin_simplification.setValue(1.0)
        self._spin_simplification.setEnabled(False)
        tiles_form.addRow("Tolerance:", self._spin_simplification)

        self._tiles_options.setVisible(False)
        layout.addWidget(self._tiles_options)

        # STAC
        self._chk_stac = QCheckBox("STAC catalog")
        layout.addWidget(self._chk_stac)

        self._stac_options = QGroupBox()
        self._stac_options.setFlat(True)
        stac_form = QFormLayout(self._stac_options)
        stac_form.setContentsMargins(16, 0, 0, 0)

        self._stac_partition_combo = QComboBox()
        self._stac_partition_combo.addItem("None (flat catalog)", "none")
        self._stac_partition_combo.addItem("By column value", "custom_column")
        stac_form.addRow("Partition strategy:", self._stac_partition_combo)

        self._stac_partition_col = QLineEdit()
        self._stac_partition_col.setPlaceholderText("field_name (comma-separated, max 3 levels)")
        self._stac_partition_col.setEnabled(False)
        stac_form.addRow("Partition column(s):", self._stac_partition_col)

        self._stac_options.setVisible(False)
        layout.addWidget(self._stac_options)

        layout.addStretch()
        return w

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self):
        self._deploy_btn.clicked.connect(self._on_deploy)
        self._close_btn.clicked.connect(self.close)
        self._layer_combo.layerChanged.connect(self._on_layer_changed)
        self._chk_tiles.toggled.connect(self._tiles_options.setVisible)
        self._chk_auto_zoom.toggled.connect(self._on_auto_zoom_toggled)
        self._chk_custom_simplification.toggled.connect(self._spin_simplification.setEnabled)
        self._chk_stac.toggled.connect(self._stac_options.setVisible)
        self._stac_partition_combo.currentIndexChanged.connect(self._on_partition_strategy_changed)
        self._bbox_detect_btn.clicked.connect(self._detect_bbox)
        self._style_detect_btn.clicked.connect(self._detect_color)
        self._log_line.connect(self._append_log)
        self._progress.connect(self._update_progress)
        self._deploy_done.connect(self._on_deploy_done)
        self._deploy_error.connect(self._on_deploy_error)

    def _on_auto_zoom_toggled(self, checked: bool):
        self._spin_min_zoom.setEnabled(not checked)
        self._spin_max_zoom.setEnabled(not checked)

    def _on_partition_strategy_changed(self):
        is_column = self._stac_partition_combo.currentData() == "custom_column"
        self._stac_partition_col.setEnabled(is_column)

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------

    def _load_settings(self):
        s = QSettings()
        self._api_key_edit.setText(s.value(SETTINGS_KEY_API_KEY, ""))
        self._chk_eu.setChecked(s.value(SETTINGS_KEY_DATA_REGION, "") == "eu")
        self._chk_private.setChecked(s.value(SETTINGS_KEY_IS_PRIVATE, False, type=bool))

    def _save_settings(self):
        s = QSettings()
        s.setValue(SETTINGS_KEY_API_KEY, self._api_key_edit.text().strip())
        s.setValue(SETTINGS_KEY_DATA_REGION, "eu" if self._chk_eu.isChecked() else "default")
        s.setValue(SETTINGS_KEY_IS_PRIVATE, self._chk_private.isChecked())

    # ------------------------------------------------------------------
    # Layer change → auto-fill / auto-detect
    # ------------------------------------------------------------------

    def _on_layer_changed(self, layer):
        if not layer:
            return
        if not self._name_edit.text():
            self._name_edit.setText(layer.name())
        if not self._slug_edit.text():
            raw = layer.name().lower()
            self._slug_edit.setText(re.sub(r"[^a-z0-9]+", "-", raw).strip("-"))
        self._detect_bbox()
        self._detect_color()

    def _detect_bbox(self):
        layer = self._layer_combo.currentLayer()
        if not layer:
            return
        try:
            ext = self._extent_wgs84(layer)
            self._bbox_west.setValue(ext.xMinimum())
            self._bbox_east.setValue(ext.xMaximum())
            self._bbox_south.setValue(ext.yMinimum())
            self._bbox_north.setValue(ext.yMaximum())
        except Exception:
            pass

    def _detect_color(self):
        layer = self._layer_combo.currentLayer()
        if not layer:
            return
        self._color_btn.setColor(QColor(self._layer_color(layer)))

    # ------------------------------------------------------------------
    # Layer introspection helpers
    # ------------------------------------------------------------------

    def _extent_wgs84(self, layer):
        ext = layer.extent()
        src = layer.crs()
        dst = QgsCoordinateReferenceSystem("EPSG:4326")
        if src.authid() != dst.authid():
            xform = QgsCoordinateTransform(src, dst, QgsProject.instance())
            ext = xform.transformBoundingBox(ext)
        return ext

    def _layer_color(self, layer):
        try:
            renderer = layer.renderer()
            if renderer and hasattr(renderer, "symbol") and callable(renderer.symbol):
                sym = renderer.symbol()
                if sym:
                    return sym.color().name()
        except Exception:
            pass
        return DEFAULT_COLOR

    def _geometry_type_str(self, layer):
        flat = QgsWkbTypes.flatType(layer.wkbType())
        return {
            QgsWkbTypes.Point: "Point",
            QgsWkbTypes.MultiPoint: "MultiPoint",
            QgsWkbTypes.LineString: "LineString",
            QgsWkbTypes.MultiLineString: "MultiLineString",
            QgsWkbTypes.Polygon: "Polygon",
            QgsWkbTypes.MultiPolygon: "MultiPolygon",
            QgsWkbTypes.GeometryCollection: "GeometryCollection",
            QgsWkbTypes.NoGeometry: "None",
        }.get(flat, "Point")

    def _field_base_type(self, qf):
        tn = qf.typeName().lower()
        if any(x in tn for x in ("int", "serial", "long")):
            return "integer"
        if any(x in tn for x in ("float", "double", "real", "numeric", "decimal", "number")):
            return "number"
        if "bool" in tn:
            return "boolean"
        if "datetime" in tn or "timestamp" in tn:
            return "date-time"
        if "date" in tn:
            return "date"
        return "string"

    def _extract_fields(self, layer):
        skip = {"fid", "geom", "geometry", "wkb_geometry", "the_geom"}
        fields = []
        for qf in layer.fields():
            if qf.name().lower() in skip:
                continue
            fields.append({
                "id": qf.name(),
                "name": qf.name(),
                "title": qf.alias() or qf.name(),
                "description": "",
                "multiplicity": "0..1",
                "fieldType": {"kind": "primitive", "baseType": self._field_base_type(qf)},
            })
        return fields

    def _build_data_model(self, layer, name, description, color_hex):
        try:
            ext = self._extent_wgs84(layer)
            spatial_extent = {
                "westBoundLongitude": str(round(ext.xMinimum(), 6)),
                "eastBoundLongitude": str(round(ext.xMaximum(), 6)),
                "southBoundLatitude": str(round(ext.yMinimum(), 6)),
                "northBoundLatitude": str(round(ext.yMaximum(), 6)),
            }
        except Exception:
            spatial_extent = {
                "westBoundLongitude": str(self._bbox_west.value()),
                "eastBoundLongitude": str(self._bbox_east.value()),
                "southBoundLatitude": str(self._bbox_south.value()),
                "northBoundLatitude": str(self._bbox_north.value()),
            }

        keywords = [k.strip() for k in self._meta_keywords.text().split(",") if k.strip()]

        layer_obj = {
            "id": "layer_0",
            "name": name,
            "description": description,
            "geometryType": self._geometry_type_str(layer),
            "geometryColumnName": "geom",
            "primaryKeyColumn": "fid",
            "properties": self._extract_fields(layer),
            "style": {
                "type": "simple",
                "simpleColor": color_hex,
            },
        }

        return {
            "name": name,
            "namespace": re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"),
            "description": description,
            "version": "1.0.0",
            "crs": layer.crs().authid() or "EPSG:4326",
            "layers": [layer_obj],
            "metadata": {
                "contactName": self._meta_contact_name.text().strip(),
                "contactEmail": self._meta_contact_email.text().strip(),
                "contactOrganization": self._meta_contact_org.text().strip(),
                "keywords": keywords,
                "theme": self._meta_theme.text().strip(),
                "license": self._meta_license.text().strip(),
                "accessRights": self._meta_access_rights.text().strip(),
                "purpose": self._meta_purpose.toPlainText().strip(),
                "accrualPeriodicity": self._meta_periodicity.text().strip(),
                "temporalExtentFrom": self._meta_temporal_from.text().strip(),
                "temporalExtentTo": self._meta_temporal_to.text().strip(),
                "url": self._meta_url.text().strip(),
                "termsOfService": self._meta_terms.text().strip(),
                "spatialExtent": spatial_extent,
            },
        }

    # ------------------------------------------------------------------
    # Deploy
    # ------------------------------------------------------------------

    def _on_deploy(self):
        api_key = self._api_key_edit.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Waystones Cloud", "Please enter your API key.")
            return

        layer = self._layer_combo.currentLayer()
        if not layer:
            QMessageBox.warning(self, "Waystones Cloud", "Please select a layer.")
            return

        name = self._name_edit.text().strip() or layer.name()
        slug = self._slug_edit.text().strip()
        if not slug:
            QMessageBox.warning(self, "Waystones Cloud", "Please enter a slug.")
            return

        services = []
        if self._chk_oapif.isChecked():
            services.append("oapif")

        generate_tiles = self._chk_tiles.isChecked()
        generate_stac = self._chk_stac.isChecked()

        if not services and not generate_tiles and not generate_stac:
            QMessageBox.warning(self, "Waystones Cloud", "Select at least one service.")
            return

        auto_zoom = self._chk_auto_zoom.isChecked()
        min_zoom = self._spin_min_zoom.value()
        max_zoom = self._spin_max_zoom.value()
        if not auto_zoom and min_zoom > max_zoom:
            QMessageBox.warning(self, "Waystones Cloud", "Min zoom must be ≤ max zoom.")
            return

        simplification = (
            self._spin_simplification.value()
            if self._chk_custom_simplification.isChecked()
            else None
        )

        partition_strategy = None
        partition_column = None
        if generate_stac:
            partition_strategy = self._stac_partition_combo.currentData()
            if partition_strategy == "custom_column":
                partition_column = self._stac_partition_col.text().strip() or None

        data_model = self._build_data_model(
            layer,
            name,
            self._desc_edit.toPlainText().strip(),
            self._color_btn.color().name(),
        )

        self._save_settings()
        self._set_busy(True)
        self._log.clear()
        self._poll_log_offset = 0

        threading.Thread(
            target=self._run_deploy,
            args=(
                api_key, layer, name, slug, services,
                generate_tiles, generate_stac,
                auto_zoom, min_zoom, max_zoom, simplification,
                "eu" if self._chk_eu.isChecked() else "default",
                self._chk_private.isChecked(),
                data_model, partition_strategy, partition_column,
            ),
            daemon=True,
        ).start()

    def _run_deploy(
        self, api_key, layer, name, slug, services,
        generate_tiles, generate_stac,
        auto_zoom, min_zoom, max_zoom, simplification,
        data_region, is_private,
        data_model, partition_strategy, partition_column,
    ):
        gpkg_path = None
        tmp_dir = None
        try:
            api = WaystonesAPI(api_key)

            self._log_line.emit("Exporting layer to GeoPackage…")
            tmp_dir = tempfile.mkdtemp()
            gpkg_path = os.path.join(tmp_dir, f"{slug}.gpkg")
            self._export_layer(layer, gpkg_path)
            self._log_line.emit(f"Exported: {os.path.getsize(gpkg_path) // 1024} KB")

            self._log_line.emit("Requesting upload URL…")
            upload_info = api.get_upload_url(
                filename=os.path.basename(gpkg_path),
                is_private=is_private,
                data_region=data_region,
            )
            presigned_url = upload_info["presignedUrl"]
            object_key = upload_info["objectKey"]

            self._log_line.emit("Uploading…")
            file_size = os.path.getsize(gpkg_path)
            api.upload_file(
                presigned_url, gpkg_path,
                progress_callback=lambda done, total: self._progress.emit(done, total),
            )
            self._log_line.emit("Upload complete.")

            self._log_line.emit("Creating project…")
            project = api.create_project(
                name=name,
                object_key=object_key,
                file_size_bytes=file_size,
                is_private=is_private,
                data_region=data_region,
                data_model=data_model,
                partition_strategy=partition_strategy,
                partition_column=partition_column,
            )
            project_id = project["id"]
            self._log_line.emit(f"Project ID: {project_id}")

            if generate_tiles:
                self._log_line.emit("Queuing tile generation…")
                api.generate_tiles(
                    project_id,
                    auto_zoom=auto_zoom,
                    min_zoom=min_zoom,
                    max_zoom=max_zoom,
                    simplification=simplification,
                )

            if generate_stac:
                self._log_line.emit("Queuing STAC generation…")
                api.generate_stac(project_id)

            if services:
                self._log_line.emit(f"Deploying with slug '{slug}'…")
                deploy_result = api.deploy(project_id, slug, services)
                self._deployment_id = deploy_result["deploymentId"]
                self._log_line.emit(f"Deployment queued: {self._deployment_id}")
                QTimer.singleShot(0, self._start_poll)
            else:
                self._deploy_done.emit("")

        except WaystonesAPIError as e:
            self._deploy_error.emit(str(e))
        except Exception as e:
            self._deploy_error.emit(f"Unexpected error: {e}")
        finally:
            try:
                if gpkg_path:
                    os.remove(gpkg_path)
                if tmp_dir:
                    os.rmdir(tmp_dir)
            except Exception:
                pass

    def _export_layer(self, layer, dest_path):
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.fileEncoding = "UTF-8"
        error, msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer, dest_path, QgsProject.instance().transformContext(), options
        )
        if error != QgsVectorFileWriter.NoError:
            raise RuntimeError(f"Layer export failed: {msg}")

    # ------------------------------------------------------------------
    # Deployment polling
    # ------------------------------------------------------------------

    def _start_poll(self):
        self._api_for_poll = WaystonesAPI(self._api_key_edit.text().strip())
        self._poll_timer.start(POLL_INTERVAL_MS)
        self._poll_deployment()

    def _poll_deployment(self):
        if not self._deployment_id:
            return
        try:
            data = self._api_for_poll.get_deployment(self._deployment_id)
        except WaystonesAPIError as e:
            self._on_deploy_error(str(e))
            return

        logs = data.get("pipeline_log") or []
        for line in logs[self._poll_log_offset:]:
            self._append_log(line)
        self._poll_log_offset = len(logs)

        status = data.get("status", "")
        if status == "ready":
            self._poll_timer.stop()
            self._deploy_done.emit(data.get("public_url") or "")
        elif status in ("failed", "deleted"):
            self._poll_timer.stop()
            self._deploy_error.emit(data.get("error_message") or f"Deployment {status}.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_busy(self, busy: bool):
        self._deploy_btn.setEnabled(not busy)
        self._progress_bar.setVisible(busy)
        if not busy:
            self._progress_bar.setValue(0)

    def _append_log(self, text: str):
        self._log.append(text)

    def _update_progress(self, done: int, total: int):
        if total > 0:
            self._progress_bar.setValue(int(done / total * 100))

    def _on_deploy_done(self, public_url: str):
        self._set_busy(False)
        msg = "Deployment is live!"
        if public_url:
            msg += f"\n\n{public_url}"
        QMessageBox.information(self, "Waystones Cloud", msg)

    def _on_deploy_error(self, message: str):
        self._poll_timer.stop()
        self._set_busy(False)
        self._append_log(f"ERROR: {message}")
        QMessageBox.critical(self, "Waystones Cloud", message)
