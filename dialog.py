import os
import re
import tempfile
import threading

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QComboBox,
    QTextEdit, QProgressBar, QGroupBox, QSizePolicy,
    QMessageBox,
)
from qgis.PyQt.QtCore import Qt, QSettings, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QFont
from qgis.gui import QgsMapLayerComboBox
from qgis.core import (
    QgsMapLayerProxyModel, QgsVectorFileWriter, QgsProject,
    QgsVectorLayer,
)

from .api import WaystonesAPI, WaystonesAPIError

SETTINGS_KEY_API_KEY = "waystones_cloud/api_key"
SETTINGS_KEY_DATA_REGION = "waystones_cloud/data_region"
POLL_INTERVAL_MS = 5000


class WaystonesDialog(QDialog):
    # Signals emitted from background thread → Qt slots on main thread
    _log_line = pyqtSignal(str)
    _progress = pyqtSignal(int, int)
    _deploy_done = pyqtSignal(str)   # public_url
    _deploy_error = pyqtSignal(str)  # error message

    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.setWindowTitle("Publish to Waystones Cloud")
        self.setMinimumWidth(480)
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
        root.setSpacing(12)

        # --- Credentials group ---
        creds = QGroupBox("Account")
        creds_form = QFormLayout(creds)
        self._api_key_edit = QLineEdit()
        self._api_key_edit.setEchoMode(QLineEdit.Password)
        self._api_key_edit.setPlaceholderText("wc_…")
        creds_form.addRow("API key:", self._api_key_edit)
        root.addWidget(creds)

        # --- Source group ---
        source = QGroupBox("Source layer")
        source_form = QFormLayout(source)
        self._layer_combo = QgsMapLayerComboBox()
        self._layer_combo.setFilters(QgsMapLayerProxyModel.VectorLayer)
        source_form.addRow("Layer:", self._layer_combo)
        root.addWidget(source)

        # --- Project group ---
        proj = QGroupBox("Project")
        proj_form = QFormLayout(proj)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("My dataset")
        proj_form.addRow("Name:", self._name_edit)

        self._slug_edit = QLineEdit()
        self._slug_edit.setPlaceholderText("my-dataset")
        proj_form.addRow("Slug:", self._slug_edit)

        self._region_combo = QComboBox()
        self._region_combo.addItem("Default (US)", "default")
        self._region_combo.addItem("EU", "eu")
        proj_form.addRow("Data region:", self._region_combo)

        root.addWidget(proj)

        # --- Services group ---
        services = QGroupBox("Services to deploy")
        svc_layout = QVBoxLayout(services)
        self._chk_oapif = QCheckBox("OGC API Features (OAPIF)")
        self._chk_oapif.setChecked(True)
        self._chk_tiles = QCheckBox("Vector tiles")
        self._chk_stac = QCheckBox("STAC catalog")
        svc_layout.addWidget(self._chk_oapif)
        svc_layout.addWidget(self._chk_tiles)
        svc_layout.addWidget(self._chk_stac)
        root.addWidget(services)

        # --- Progress ---
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        root.addWidget(self._progress_bar)

        # --- Log output ---
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(140)
        mono = QFont("Courier New", 9)
        mono.setStyleHint(QFont.Monospace)
        self._log.setFont(mono)
        root.addWidget(self._log)

        # --- Buttons ---
        btn_row = QHBoxLayout()
        self._deploy_btn = QPushButton("Deploy")
        self._deploy_btn.setDefault(True)
        self._close_btn = QPushButton("Close")
        btn_row.addStretch()
        btn_row.addWidget(self._close_btn)
        btn_row.addWidget(self._deploy_btn)
        root.addLayout(btn_row)

    def _connect_signals(self):
        self._deploy_btn.clicked.connect(self._on_deploy)
        self._close_btn.clicked.connect(self.close)
        self._layer_combo.layerChanged.connect(self._on_layer_changed)
        self._log_line.connect(self._append_log)
        self._progress.connect(self._update_progress)
        self._deploy_done.connect(self._on_deploy_done)
        self._deploy_error.connect(self._on_deploy_error)

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------

    def _load_settings(self):
        s = QSettings()
        self._api_key_edit.setText(s.value(SETTINGS_KEY_API_KEY, ""))
        region = s.value(SETTINGS_KEY_DATA_REGION, "default")
        idx = self._region_combo.findData(region)
        if idx >= 0:
            self._region_combo.setCurrentIndex(idx)

    def _save_settings(self):
        s = QSettings()
        s.setValue(SETTINGS_KEY_API_KEY, self._api_key_edit.text().strip())
        s.setValue(SETTINGS_KEY_DATA_REGION, self._region_combo.currentData())

    # ------------------------------------------------------------------
    # Layer change → pre-fill name
    # ------------------------------------------------------------------

    def _on_layer_changed(self, layer):
        if layer and not self._name_edit.text():
            self._name_edit.setText(layer.name())
        if layer and not self._slug_edit.text():
            raw = layer.name().lower()
            slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
            self._slug_edit.setText(slug)

    # ------------------------------------------------------------------
    # Deploy button
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
        if not services:
            QMessageBox.warning(self, "Waystones Cloud", "Select at least one service.")
            return

        generate_tiles = self._chk_tiles.isChecked()
        generate_stac = self._chk_stac.isChecked()
        data_region = self._region_combo.currentData()

        self._save_settings()
        self._set_busy(True)
        self._log.clear()
        self._poll_log_offset = 0

        threading.Thread(
            target=self._run_deploy,
            args=(api_key, layer, name, slug, services, generate_tiles, generate_stac, data_region),
            daemon=True,
        ).start()

    def _run_deploy(self, api_key, layer, name, slug, services, generate_tiles, generate_stac, data_region):
        try:
            api = WaystonesAPI(api_key)

            # 1. Export layer to a temporary GeoPackage
            self._log_line.emit("Exporting layer to GeoPackage…")
            tmp_dir = tempfile.mkdtemp()
            gpkg_path = os.path.join(tmp_dir, f"{slug}.gpkg")
            self._export_layer(layer, gpkg_path)
            self._log_line.emit(f"Exported: {os.path.getsize(gpkg_path) // 1024} KB")

            # 2. Get presigned upload URL
            self._log_line.emit("Requesting upload URL…")
            upload_info = api.get_upload_url(
                filename=os.path.basename(gpkg_path),
                data_region=data_region,
            )
            presigned_url = upload_info["presignedUrl"]
            object_key = upload_info["objectKey"]

            # 3. Upload to R2
            self._log_line.emit("Uploading…")
            file_size = os.path.getsize(gpkg_path)
            api.upload_file(presigned_url, gpkg_path, progress_callback=lambda done, total: self._progress.emit(done, total))
            self._log_line.emit("Upload complete.")

            # 4. Create project
            self._log_line.emit("Creating project…")
            project = api.create_project(
                name=name,
                object_key=object_key,
                file_size_bytes=file_size,
                data_region=data_region,
            )
            project_id = project["id"]
            self._log_line.emit(f"Project ID: {project_id}")

            # 5. Deploy
            self._log_line.emit(f"Deploying with slug '{slug}'…")
            deploy_result = api.deploy(project_id, slug, services)
            self._deployment_id = deploy_result["deploymentId"]
            self._log_line.emit(f"Deployment queued: {self._deployment_id}")

            # 6. Optional: trigger tiles / STAC (fire-and-forget; they run in background)
            if generate_tiles:
                self._log_line.emit("Queuing tile generation…")
                api.generate_tiles(project_id)
            if generate_stac:
                self._log_line.emit("Queuing STAC generation…")
                api.generate_stac(project_id)

            # 7. Start polling timer on main thread
            QTimer.singleShot(0, self._start_poll)

        except WaystonesAPIError as e:
            self._deploy_error.emit(str(e))
        except Exception as e:
            self._deploy_error.emit(f"Unexpected error: {e}")
        finally:
            try:
                os.remove(gpkg_path)
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
    # Deployment polling (runs on main thread via QTimer)
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
