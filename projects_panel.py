import re
import threading
import time
from urllib.parse import urlparse

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QScrollArea,
    QLineEdit, QPushButton, QCheckBox, QComboBox, QInputDialog,
    QTextEdit, QSpinBox, QLabel, QMessageBox, QDoubleSpinBox, QFrame,
    QListWidget, QListWidgetItem, QDialog,
)
from PyQt6.QtCore import QTimer, pyqtSignal, Qt
from PyQt6.QtGui import QColor
from qgis.gui import QgsColorButton

from .api import WaystonesAPI, WaystonesAPIError
from .options import THEMES, LICENSES, ACCESS_RIGHTS, PERIODICITIES
from .styles import MSGBOX_QSS
from .widgets import make_combo, make_domain_combo, card_frame, endpoint_frame, endpoint_row


class ProjectsPanel(QWidget):
    """The 'Projects' tab: lists existing projects and renders the detail/manage views.

    Decoupled from the main dialog via four callables passed at construction:
      get_api_key()    -> current API key (stripped)
      log(text)        -> append a line to the shared log (thread-safe)
      request_replace(project) -> ask the dialog to start the Replace-GPKG flow
      checked_extent() -> {"west","east","south","north"} from checked layers, or None
    """

    _projects_loaded = pyqtSignal(list)
    _projects_load_err = pyqtSignal(str)
    _project_fetched = pyqtSignal(dict)
    _project_fetch_err = pyqtSignal(str)

    def __init__(self, get_api_key, log, request_replace, checked_extent, parent=None):
        super().__init__(parent)
        self._get_api_key = get_api_key
        self._log = log
        self._request_replace = request_replace
        self._checked_extent = checked_extent
        self._selected_project: dict | None = None

        self._build_ui()

        self._projects_loaded.connect(self._on_projects_loaded)
        self._projects_load_err.connect(self._on_projects_load_err)
        self._project_fetched.connect(self._show_project_detail)
        self._project_fetch_err.connect(self._on_project_fetch_err)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        hdr = QWidget()
        hdr.setStyleSheet("background: #f8fafc; border-bottom: 1px solid #e2e8f0;")
        hdr_row = QHBoxLayout(hdr)
        hdr_row.setContentsMargins(16, 10, 16, 10)
        hdr_lbl = QLabel("Your Projects")
        hdr_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #1e293b;")
        hdr_row.addWidget(hdr_lbl)
        hdr_row.addStretch()
        self._refresh_btn = QPushButton("↻  Refresh")
        self._refresh_btn.setObjectName("smallBtn")
        self._refresh_btn.clicked.connect(self.load_projects)
        hdr_row.addWidget(self._refresh_btn)
        layout.addWidget(hdr)

        # Split: list left, detail right
        split = QHBoxLayout()
        split.setContentsMargins(0, 0, 0, 0)
        split.setSpacing(0)

        self._projects_list = QListWidget()
        self._projects_list.setObjectName("projectsList")
        self._projects_list.setFixedWidth(210)
        self._projects_list.currentItemChanged.connect(self._on_project_selected)
        split.addWidget(self._projects_list)

        self._detail_scroll = QScrollArea()
        self._detail_scroll.setWidgetResizable(True)
        self._detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        placeholder = QLabel("Select a project to view details.")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("color: #94a3b8; font-size: 12px;")
        self._detail_scroll.setWidget(placeholder)
        split.addWidget(self._detail_scroll, 1)

        layout.addLayout(split, 1)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_if_empty(self):
        if self._projects_list.count() == 0:
            self.load_projects()

    def load_projects(self):
        api_key = self._get_api_key()
        if not api_key:
            return
        self._projects_list.clear()
        loading = QListWidgetItem("Loading…")
        loading.setForeground(QColor("#94a3b8"))
        self._projects_list.addItem(loading)

        def _fetch():
            try:
                api = WaystonesAPI(api_key)
                self._projects_loaded.emit(api.list_projects())
            except WaystonesAPIError as e:
                self._projects_load_err.emit(str(e))

        threading.Thread(target=_fetch, daemon=True).start()

    def _on_projects_loaded(self, projects: list):
        self._projects_list.clear()
        if not projects:
            empty = QListWidgetItem("No projects yet.")
            empty.setForeground(QColor("#94a3b8"))
            self._projects_list.addItem(empty)
            return
        for p in projects:
            item = QListWidgetItem(p.get("name", p["id"]))
            item.setData(Qt.ItemDataRole.UserRole, p["id"])
            self._projects_list.addItem(item)

    def _on_projects_load_err(self, msg: str):
        self._projects_list.clear()
        err = QListWidgetItem(f"Error: {msg}")
        err.setForeground(QColor("#dc2626"))
        self._projects_list.addItem(err)

    def _on_project_selected(self, current, previous):
        if not current:
            return
        project_id = current.data(Qt.ItemDataRole.UserRole)
        if not project_id:
            return
        api_key = self._get_api_key()
        if not api_key:
            return

        loading = QLabel("Loading…")
        loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading.setStyleSheet("color: #94a3b8; font-size: 12px;")
        self._detail_scroll.setWidget(loading)

        def _fetch():
            try:
                api = WaystonesAPI(api_key)
                self._project_fetched.emit(api.get_project(project_id))
            except WaystonesAPIError as e:
                self._project_fetch_err.emit(str(e))

        threading.Thread(target=_fetch, daemon=True).start()

    def _on_project_fetch_err(self, msg: str):
        err = QLabel(f"Failed to load project: {msg}")
        err.setAlignment(Qt.AlignmentFlag.AlignCenter)
        err.setStyleSheet("color: #dc2626; font-size: 12px;")
        self._detail_scroll.setWidget(err)

    # ------------------------------------------------------------------
    # Project detail
    # ------------------------------------------------------------------

    def _show_project_detail(self, project: dict):
        self._selected_project = project

        w = QWidget()
        w.setStyleSheet("background: white;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        name_lbl = QLabel(project.get("name", "Untitled"))
        name_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #1e293b;")
        layout.addWidget(name_lbl)

        deployments = [d for d in (project.get("deployments") or [])
                       if d.get("status") not in ("deleted", "deleting")]

        # ── Deployment section ─────────────────────────────────────
        dep_frame = card_frame()
        dep_layout = QVBoxLayout(dep_frame)
        dep_layout.setContentsMargins(14, 12, 14, 12)
        dep_layout.setSpacing(8)

        dep_title = QLabel("DEPLOYMENT")
        dep_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.05em; background: transparent;")
        dep_layout.addWidget(dep_title)

        project_id = project["id"]

        if deployments:
            dep = deployments[0]
            status = dep.get("status", "unknown")
            slug = dep.get("slug", "")
            domain = dep.get("service_domain", "waystones.cloud")
            services = dep.get("services") or []
            public_url = dep.get("public_url") or f"https://{slug}.{domain}"
            dep_id = dep["id"]

            status_color = "#6366f1" if status == "ready" else "#f59e0b" if "deploy" in status else "#dc2626"

            has_tiles = "tiles" in services or (project.get("tile_size_bytes") or 0) > 0
            has_stac = "stac" in services or (project.get("stac_catalog_size_bytes") or 0) > 0

            all_svcs = list(services)
            if has_tiles and "tiles" not in all_svcs:
                all_svcs.append("tiles")
            if has_stac and "stac" not in all_svcs:
                all_svcs.append("stac")
            svc_str = "  ·  ".join(s.upper() for s in all_svcs) or "none"
            status_lbl = QLabel(f'<span style="color:{status_color}">● {status.capitalize()}</span>  &nbsp; {svc_str}')
            status_lbl.setStyleSheet("font-size: 11px; background: transparent;")
            dep_layout.addWidget(status_lbl)

            # Derive tiles style filename from project name using the same slugify as the worker
            _pname = project.get("name") or ""
            _tiles_slug = re.sub(r"[^a-z0-9]+", "-", _pname.lower()).strip("-") or "combined"
            tiles_style_url = f"{public_url}/tiles/{_tiles_slug}.styles.json"

            # ── API endpoints (for QGIS / dev use) ────────────────
            api_eps = []
            if "oapif" in services:
                api_eps.append(("OAPIF", public_url, False))
            if has_tiles:
                api_eps.append(("Tiles", tiles_style_url, False))
            if has_stac:
                api_eps.append(("STAC", f"{public_url}/stac/catalog.json", False))
            if "qgis" in services:
                api_eps.append(("WMS", f"{public_url}/ows/?SERVICE=WMS&REQUEST=GetCapabilities", False))

            if api_eps:
                af, al = endpoint_frame("API ENDPOINTS")
                for lbl, url, ext in api_eps:
                    endpoint_row(al, lbl, url, open_ext=ext)
                dep_layout.addWidget(af)

            # ── Web viewer links ───────────────────────────────────
            viewer_eps = []
            if "oapif" in services:
                viewer_eps.append(("OAPIF", public_url))
            if has_tiles:
                viewer_eps.append(("Tiles", f"{public_url}/tiles"))
            if has_stac:
                viewer_eps.append(("STAC", f"{public_url}/stac"))

            if viewer_eps:
                vf, vl = endpoint_frame("WEB VIEWER")
                for lbl, url in viewer_eps:
                    endpoint_row(vl, lbl, url, open_ext=True)
                dep_layout.addWidget(vf)

            btn_row = QHBoxLayout()
            chg_btn = QPushButton("Change Services…")
            chg_btn.setObjectName("smallBtn")
            chg_btn.clicked.connect(
                lambda _=False, p=project, d=dep: self._show_redeploy_form(p, d)
            )
            remove_btn = QPushButton("Remove Services")
            remove_btn.setObjectName("smallBtn")
            remove_btn.clicked.connect(lambda _=False, did=dep_id: self._on_remove_services(did))
            btn_row.addWidget(chg_btn)
            btn_row.addWidget(remove_btn)
            btn_row.addStretch()
            dep_layout.addLayout(btn_row)

            # Regen buttons — shown whenever tiles/stac data exists
            regen_items = []
            if has_tiles:
                regen_tiles_btn = QPushButton("↻  Tiles")
                regen_tiles_btn.setObjectName("smallBtn")
                regen_tiles_btn.clicked.connect(lambda _=False, pid=project_id: self._on_regen_tiles(pid))
                regen_items.append(regen_tiles_btn)
            if has_stac:
                regen_stac_btn = QPushButton("↻  STAC")
                regen_stac_btn.setObjectName("smallBtn")
                regen_stac_btn.clicked.connect(lambda _=False, pid=project_id: self._on_regen_stac(pid))
                regen_items.append(regen_stac_btn)
            if regen_items:
                regen_row = QHBoxLayout()
                regen_lbl = QLabel("Regenerate:")
                regen_lbl.setStyleSheet("font-size: 11px; color: #64748b; background: transparent;")
                regen_row.addWidget(regen_lbl)
                for btn in regen_items:
                    regen_row.addWidget(btn)
                regen_row.addStretch()
                dep_layout.addLayout(regen_row)
        else:
            no_dep = QLabel("No active deployment.")
            no_dep.setStyleSheet("color: #94a3b8; font-size: 11px; background: transparent;")
            dep_layout.addWidget(no_dep)

            deploy_btn = QPushButton("Deploy…")
            deploy_btn.setObjectName("smallBtn")
            deploy_btn.clicked.connect(
                lambda _=False, p=project: self._show_redeploy_form(p, None)
            )
            dep_layout.addWidget(deploy_btn)

        layout.addWidget(dep_frame)

        # ── File section ───────────────────────────────────────────
        file_frame = card_frame()
        file_layout = QVBoxLayout(file_frame)
        file_layout.setContentsMargins(14, 12, 14, 12)
        file_layout.setSpacing(8)

        file_title = QLabel("SOURCE FILE")
        file_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.05em; background: transparent;")
        file_layout.addWidget(file_title)

        size_bytes = project.get("file_size_bytes") or 0
        size_lbl = QLabel(f"{size_bytes // 1024} KB  ·  GeoPackage")
        size_lbl.setStyleSheet("font-size: 11px; color: #374151; background: transparent;")
        file_layout.addWidget(size_lbl)

        replace_btn = QPushButton("Replace GPKG…")
        replace_btn.setObjectName("smallBtn")
        replace_btn.clicked.connect(lambda _=False, p=project: self._request_replace(p))
        file_layout.addWidget(replace_btn)

        layout.addWidget(file_frame)

        # ── Metadata section ───────────────────────────────────────
        meta_frame = card_frame()
        meta_layout = QVBoxLayout(meta_frame)
        meta_layout.setContentsMargins(14, 12, 14, 12)
        meta_layout.setSpacing(8)

        meta_title = QLabel("METADATA")
        meta_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.05em; background: transparent;")
        meta_layout.addWidget(meta_title)

        dm = project.get("data_model") or {}
        layers = dm.get("layers") or []
        n_layers = len(layers)
        desc = dm.get("description") or ""
        summary = desc[:60] + "…" if len(desc) > 60 else desc if desc else f"{n_layers} layer(s)"
        meta_lbl = QLabel(summary)
        meta_lbl.setStyleSheet("font-size: 11px; color: #374151; background: transparent;")
        meta_layout.addWidget(meta_lbl)

        edit_meta_btn = QPushButton("Edit Metadata…")
        edit_meta_btn.setObjectName("smallBtn")
        edit_meta_btn.clicked.connect(lambda _=False, p=project: self._show_metadata_edit(p))
        meta_layout.addWidget(edit_meta_btn)

        layout.addWidget(meta_frame)

        # ── API Keys section (private projects only) ───────────────
        if project.get("is_private"):
            layout.addWidget(self._build_api_keys_section(project_id, self._get_api_key()))

        layout.addStretch()

        # ── Danger zone ────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #fca5a5;")
        layout.addWidget(sep)

        delete_btn = QPushButton("Delete Project…")
        delete_btn.setObjectName("dangerBtn")
        delete_btn.clicked.connect(lambda _=False, p=project: self._on_delete_project(p))
        layout.addWidget(delete_btn)

        self._detail_scroll.setWidget(w)

    def _on_delete_project(self, project: dict):
        name = project.get("name") or project["id"]
        project_id = project["id"]

        dlg = QDialog(self)
        dlg.setWindowTitle("Delete Project")
        dlg.setMinimumWidth(400)
        dlg.setStyleSheet("QDialog { background: white; }")

        v = QVBoxLayout(dlg)
        v.setContentsMargins(20, 20, 20, 16)
        v.setSpacing(12)

        # Warning banner
        banner = QFrame()
        banner.setStyleSheet(
            "QFrame { background: #fef2f2; border: 1px solid #fca5a5; border-radius: 8px; }"
        )
        bl = QVBoxLayout(banner)
        bl.setContentsMargins(14, 10, 14, 10)
        bl.setSpacing(4)
        warn_title = QLabel("This action is permanent and cannot be undone.")
        warn_title.setStyleSheet("font-weight: 700; color: #991b1b; background: transparent;")
        warn_body = QLabel(
            f"Deleting <b>{name}</b> will remove the project, all uploaded data, "
            "deployments, tiles, and STAC catalogs."
        )
        warn_body.setWordWrap(True)
        warn_body.setStyleSheet("color: #7f1d1d; background: transparent;")
        bl.addWidget(warn_title)
        bl.addWidget(warn_body)
        v.addWidget(banner)

        confirm_lbl = QLabel(f'Type <b>{name}</b> to confirm:')
        confirm_lbl.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(confirm_lbl)

        confirm_edit = QLineEdit()
        confirm_edit.setPlaceholderText(name)
        v.addWidget(confirm_edit)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("smallBtn")
        delete_btn = QPushButton("Delete Project")
        delete_btn.setObjectName("dangerBtn")
        delete_btn.setEnabled(False)
        delete_btn.setStyleSheet(
            "QPushButton { background: #dc2626; border: none; color: white;"
            " border-radius: 6px; padding: 5px 14px; font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { background: #b91c1c; }"
            "QPushButton:disabled { background: #fca5a5; color: white; }"
        )
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(delete_btn)
        v.addLayout(btn_row)

        confirm_edit.textChanged.connect(
            lambda text: delete_btn.setEnabled(text == name)
        )
        cancel_btn.clicked.connect(dlg.reject)
        delete_btn.clicked.connect(dlg.accept)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        api_key = self._get_api_key()

        def _run():
            try:
                WaystonesAPI(api_key).delete_project(project_id)
                self._log(f"Project '{name}' deleted.")
                self._projects_loaded.emit([
                    p for p in (WaystonesAPI(api_key).list_projects() or [])
                    if p["id"] != project_id
                ])
                placeholder = QLabel("Project deleted.")
                placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
                placeholder.setStyleSheet("color: #94a3b8; font-size: 12px;")
                QTimer.singleShot(0, lambda: self._detail_scroll.setWidget(placeholder))
            except WaystonesAPIError as e:
                self._log(f"ERROR deleting project: {e}")

        threading.Thread(target=_run, daemon=True).start()

    def _build_api_keys_section(self, project_id: str, api_key: str) -> QFrame:
        keys_frame = card_frame()
        keys_layout = QVBoxLayout(keys_frame)
        keys_layout.setContentsMargins(14, 12, 14, 12)
        keys_layout.setSpacing(8)

        keys_title = QLabel("API KEYS")
        keys_title.setStyleSheet(
            "font-size: 10px; font-weight: 700; color: #94a3b8;"
            " letter-spacing: 0.05em; background: transparent;"
        )
        keys_layout.addWidget(keys_title)

        keys_list_layout = QVBoxLayout()
        keys_list_layout.setSpacing(4)
        keys_list_placeholder = QLabel("Loading…")
        keys_list_placeholder.setStyleSheet("font-size: 11px; color: #94a3b8; background: transparent;")
        keys_list_layout.addWidget(keys_list_placeholder)
        keys_layout.addLayout(keys_list_layout)

        add_key_btn = QPushButton("+ New API Key…")
        add_key_btn.setObjectName("smallBtn")
        keys_layout.addWidget(add_key_btn)

        def _rebuild_keys_list(keys: list):
            while keys_list_layout.count():
                item = keys_list_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            if not keys:
                lbl = QLabel("No API keys — add one below.")
                lbl.setStyleSheet("font-size: 11px; color: #94a3b8; background: transparent;")
                keys_list_layout.addWidget(lbl)
                return
            for k in keys:
                row = QHBoxLayout()
                label_text = k.get("label", "")
                prefix = k.get("prefix", "")
                last_used = k.get("last_used_at")
                last_used_str = f"  last used {last_used[:10]}" if last_used else "  never used"
                lbl = QLabel(
                    f"<b>{label_text}</b>"
                    f"  <span style='color:#94a3b8;font-size:10px;'>{prefix}…{last_used_str}</span>"
                )
                lbl.setStyleSheet("font-size: 11px; background: transparent;")
                revoke_btn = QPushButton("Revoke")
                revoke_btn.setObjectName("smallBtn")
                revoke_btn.setMaximumWidth(54)
                key_id = k["id"]
                revoke_btn.clicked.connect(lambda _=False, kid=key_id: _on_revoke(kid))
                row.addWidget(lbl, 1)
                row.addWidget(revoke_btn)
                keys_list_layout.addLayout(row)

        def _load_keys():
            try:
                keys = WaystonesAPI(api_key).list_project_api_keys(project_id)
                QTimer.singleShot(0, lambda k=keys: _rebuild_keys_list(k))
            except WaystonesAPIError as e:
                err = str(e)
                QTimer.singleShot(0, lambda: keys_list_placeholder.setText(f"Error: {err}"))

        def _on_revoke(key_id: str):
            msg = QMessageBox(self)
            msg.setWindowTitle("Revoke API Key")
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setStyleSheet(MSGBOX_QSS)
            msg.setText("Revoke this API key?")
            msg.setInformativeText("Any client using this key will immediately lose access.")
            msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
            msg.setDefaultButton(QMessageBox.StandardButton.Cancel)
            if msg.exec() != QMessageBox.StandardButton.Yes:
                return
            def _run():
                try:
                    WaystonesAPI(api_key).revoke_project_api_key(project_id, key_id)
                    _load_keys()
                except WaystonesAPIError as e:
                    err = str(e)
                    QTimer.singleShot(0, lambda: self._log(f"Revoke failed: {err}"))
            threading.Thread(target=_run, daemon=True).start()

        def _on_add_key():
            label, ok = QInputDialog.getText(self, "New API Key", "Key label (e.g. 'QGIS Desktop'):")
            if not ok or not label.strip():
                return
            def _run():
                try:
                    result = WaystonesAPI(api_key).create_project_api_key(project_id, label.strip())
                    cleartext = result.get("key", "")
                    QTimer.singleShot(0, lambda: _show_new_key(result.get("label", label), cleartext))
                    _load_keys()
                except WaystonesAPIError as e:
                    err = str(e)
                    QTimer.singleShot(0, lambda: self._log(f"Create key failed: {err}"))
            threading.Thread(target=_run, daemon=True).start()

        def _show_new_key(label: str, cleartext: str):
            msg = QMessageBox(self)
            msg.setWindowTitle("API Key Created")
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setStyleSheet(MSGBOX_QSS)
            msg.setText(f"Key <b>{label}</b> created. Copy it now — it won't be shown again.")
            msg.setInformativeText(cleartext)
            msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            copy_btn = msg.addButton("Copy & Close", QMessageBox.ButtonRole.AcceptRole)
            msg.addButton("Close", QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            if msg.clickedButton() == copy_btn:
                QApplication.clipboard().setText(cleartext)

        add_key_btn.clicked.connect(_on_add_key)
        threading.Thread(target=_load_keys, daemon=True).start()
        return keys_frame

    # ------------------------------------------------------------------
    # Redeploy / change services
    # ------------------------------------------------------------------

    def _show_redeploy_form(self, project: dict, existing_dep: dict | None):
        w = QWidget()
        w.setStyleSheet("background: white;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        back_btn = QPushButton("← Back")
        back_btn.setObjectName("smallBtn")
        back_btn.clicked.connect(lambda: self._show_project_detail(project))
        layout.addWidget(back_btn)

        title = QLabel("Change Services" if existing_dep else "Deploy")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #1e293b;")
        deploy_btn = QPushButton("Deploy")
        deploy_btn.setObjectName("deployBtn")
        title_row = QHBoxLayout()
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(deploy_btn)
        layout.addLayout(title_row)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        slug_row = QHBoxLayout()
        slug_row.setSpacing(6)
        slug_edit = QLineEdit()
        slug_edit.setText(existing_dep.get("slug", project.get("name", "")) if existing_dep else "")
        cur_domain = existing_dep.get("service_domain", "waystones.cloud") if existing_dep else None
        domain_combo = make_domain_combo(cur_domain)
        slug_row.addWidget(slug_edit, 1)
        slug_row.addWidget(domain_combo)
        form.addRow("Slug: *", slug_row)

        chk_oapif = QCheckBox("OGC API Features (OAPIF)")
        chk_tiles = QCheckBox("Vector tiles")
        chk_stac  = QCheckBox("STAC catalog")

        existing_svcs = existing_dep.get("services") or [] if existing_dep else []
        tiles_already_deployed = "tiles" in existing_svcs

        if existing_dep:
            chk_oapif.setChecked("oapif" in existing_svcs)
            chk_tiles.setChecked("tiles" in existing_svcs)
            chk_stac.setChecked("stac" in existing_svcs)
        else:
            chk_oapif.setChecked(True)

        form.addRow("Services:", chk_oapif)
        form.addRow("", chk_tiles)
        form.addRow("", chk_stac)
        layout.addLayout(form)

        # ── Tiles options (shown when tiles is checked) ────────────────
        tiles_frame = QFrame()
        tiles_frame.setStyleSheet(
            "QFrame { background: #f8fafc; border: 1px solid #e2e8f0;"
            " border-radius: 6px; }"
        )
        tiles_fl = QFormLayout(tiles_frame)
        tiles_fl.setContentsMargins(12, 10, 12, 10)
        tiles_fl.setSpacing(8)
        tiles_fl.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        chk_auto_zoom = QCheckBox("Auto-detect zoom range")
        chk_auto_zoom.setChecked(True)

        _spin_ss = "QSpinBox:disabled { color: #64748b; }"
        spin_min = QSpinBox()
        spin_min.setRange(0, 22)
        spin_min.setValue(0)
        spin_min.setFixedWidth(70)
        spin_min.setStyleSheet(_spin_ss)
        spin_max = QSpinBox()
        spin_max.setRange(0, 22)
        spin_max.setValue(14)
        spin_max.setFixedWidth(70)
        spin_max.setStyleSheet(_spin_ss)

        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(6)
        zoom_row.addWidget(QLabel("Min:"))
        zoom_row.addWidget(spin_min)
        zoom_row.addSpacing(10)
        zoom_row.addWidget(QLabel("Max:"))
        zoom_row.addWidget(spin_max)
        zoom_row.addStretch()

        spin_simplify = QDoubleSpinBox()
        spin_simplify.setRange(0.0, 10.0)
        spin_simplify.setSingleStep(0.1)
        spin_simplify.setValue(0.0)
        spin_simplify.setSpecialValueText("Auto")

        zoom_hint = QLabel("Uncheck auto-detect to set manually")
        zoom_hint.setStyleSheet("font-size: 10px; color: #94a3b8; background: transparent;")

        tiles_fl.addRow("", chk_auto_zoom)
        tiles_fl.addRow("Zoom range:", zoom_row)
        tiles_fl.addRow("", zoom_hint)
        tiles_fl.addRow("Simplification:", spin_simplify)

        tiles_note = QLabel()
        tiles_note.setStyleSheet("font-size: 10px; color: #6366f1; background: transparent;")

        def _update_zoom_controls():
            manual = not chk_auto_zoom.isChecked()
            spin_min.setEnabled(manual)
            spin_max.setEnabled(manual)
            zoom_hint.setVisible(not manual)

        def _update_tiles_note():
            if not chk_tiles.isChecked():
                tiles_note.setText("")
            elif not tiles_already_deployed:
                tiles_note.setText("ℹ Tiles will be generated after deployment.")
            else:
                tiles_note.setText("ℹ Tiles already exist — settings only apply if you also Regenerate.")

        chk_auto_zoom.toggled.connect(_update_zoom_controls)
        _update_zoom_controls()

        def _toggle_tiles_frame(checked):
            tiles_frame.setVisible(checked)
            _update_tiles_note()

        chk_tiles.toggled.connect(_toggle_tiles_frame)
        tiles_frame.setVisible(chk_tiles.isChecked())
        _update_tiles_note()

        layout.addWidget(tiles_frame)
        layout.addWidget(tiles_note)

        # ── STAC options (shown when STAC is checked) ──────────────────
        stac_already_deployed = "stac" in existing_svcs

        stac_frame = QFrame()
        stac_frame.setStyleSheet(
            "QFrame { background: #f8fafc; border: 1px solid #e2e8f0;"
            " border-radius: 6px; }"
        )
        stac_fl = QFormLayout(stac_frame)
        stac_fl.setContentsMargins(12, 10, 12, 10)
        stac_fl.setSpacing(8)
        stac_fl.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        stac_strategy_combo = QComboBox()
        stac_strategy_combo.addItem("Single file (no partitioning)", "none")
        stac_strategy_combo.addItem("Split by custom column", "custom_column")

        dm = project.get("data_model") or {}
        existing_strategy = dm.get("partitionStrategy") or "none"
        existing_column = dm.get("partitionColumn") or ""
        idx = stac_strategy_combo.findData(existing_strategy)
        if idx >= 0:
            stac_strategy_combo.setCurrentIndex(idx)

        stac_col_edit = QLineEdit()
        stac_col_edit.setPlaceholderText("e.g. region, year")
        stac_col_edit.setText(existing_column)
        stac_col_row = QWidget()
        stac_col_layout = QFormLayout(stac_col_row)
        stac_col_layout.setContentsMargins(0, 0, 0, 0)
        stac_col_layout.addRow("Column(s):", stac_col_edit)

        stac_fl.addRow("Partitioning:", stac_strategy_combo)
        stac_fl.addRow("", stac_col_row)

        def _toggle_stac_col(index):
            stac_col_row.setVisible(stac_strategy_combo.itemData(index) == "custom_column")

        stac_strategy_combo.currentIndexChanged.connect(_toggle_stac_col)
        _toggle_stac_col(stac_strategy_combo.currentIndex())

        stac_note = QLabel()
        stac_note.setStyleSheet("font-size: 10px; color: #6366f1; background: transparent;")

        def _update_stac_note():
            if not chk_stac.isChecked():
                stac_note.setText("")
            elif not stac_already_deployed:
                stac_note.setText("ℹ STAC catalog will be generated after deployment.")
            else:
                stac_note.setText("ℹ STAC already exists — changing strategy regenerates the catalog.")

        def _toggle_stac_frame(checked):
            stac_frame.setVisible(checked)
            _update_stac_note()

        chk_stac.toggled.connect(_toggle_stac_frame)
        stac_frame.setVisible(chk_stac.isChecked())
        _update_stac_note()

        layout.addWidget(stac_frame)
        layout.addWidget(stac_note)

        status_lbl = QLabel()
        status_lbl.setStyleSheet("font-size: 11px;")
        layout.addWidget(status_lbl)
        layout.addStretch()

        project_id = project["id"]

        def _do_redeploy():
            slug = slug_edit.text().strip()
            domain = domain_combo.currentData()
            if not slug:
                status_lbl.setText("Enter a slug.")
                status_lbl.setStyleSheet("color: #dc2626; font-size: 11px;")
                return

            # Deploy endpoint only accepts "oapif" / "qgis"; tiles & stac are generated separately.
            deploy_svcs = []
            if chk_oapif.isChecked(): deploy_svcs.append("oapif")

            adding_tiles = chk_tiles.isChecked() and not tiles_already_deployed
            adding_stac = chk_stac.isChecked() and not stac_already_deployed

            if not deploy_svcs and not adding_tiles and not adding_stac:
                status_lbl.setText("Select at least one service.")
                status_lbl.setStyleSheet("color: #dc2626; font-size: 11px;")
                return

            auto_zoom = chk_auto_zoom.isChecked()
            min_zoom = spin_min.value()
            max_zoom = spin_max.value()
            simp = spin_simplify.value() if spin_simplify.value() > 0 else None

            stac_strategy = stac_strategy_combo.currentData()
            stac_col = stac_col_edit.text().strip() if stac_strategy == "custom_column" else None

            deploy_btn.setEnabled(False)
            status_lbl.setText("Deploying…")
            status_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
            api_key = self._get_api_key()

            def _run():
                try:
                    api = WaystonesAPI(api_key)
                    label_parts = []
                    if deploy_svcs:
                        result = api.deploy(project_id, slug, deploy_svcs, domain=domain)
                        dep_id = result.get("deploymentId", "")
                        self._log(f"Deploy queued: {slug}.{domain} — {dep_id}")
                        label_parts.append(f"{slug}.{domain}")
                    if adding_tiles:
                        api.generate_tiles(project_id, auto_zoom=auto_zoom,
                                           min_zoom=min_zoom, max_zoom=max_zoom,
                                           simplification=simp)
                        self._log("Tile generation queued.")
                        label_parts.append("tiles")
                        threading.Thread(
                            target=self._poll_tiles_status,
                            args=(api_key, project_id),
                            daemon=True,
                        ).start()
                    if adding_stac:
                        api.generate_stac(project_id, partition_strategy=stac_strategy,
                                          partition_column=stac_col)
                        self._log("STAC generation queued.")
                        label_parts.append("stac")
                        threading.Thread(
                            target=self._poll_stac_status,
                            args=(api_key, project_id),
                            daemon=True,
                        ).start()
                    done_msg = "✓ " + " + ".join(label_parts)
                    QTimer.singleShot(0, lambda: (
                        status_lbl.setText(done_msg),
                        status_lbl.setStyleSheet("color: #6366f1; font-size: 11px; font-weight: 600;"),
                    ))
                except Exception as e:
                    err = str(e)
                    self._log(f"Deploy error: {err}")
                    QTimer.singleShot(0, lambda: (
                        status_lbl.setText(f"✗ {err[:120]}"),
                        status_lbl.setStyleSheet("color: #dc2626; font-size: 11px;"),
                    ))
                finally:
                    QTimer.singleShot(0, lambda: deploy_btn.setEnabled(True))

            threading.Thread(target=_run, daemon=True).start()

        deploy_btn.clicked.connect(_do_redeploy)
        self._detail_scroll.setWidget(w)

    def _on_remove_services(self, deployment_id: str):
        msg = QMessageBox(self)
        msg.setWindowTitle("Remove Services")
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setStyleSheet(MSGBOX_QSS)
        msg.setText("Remove this deployment?")
        msg.setInformativeText(
            "The deployment URL will be freed. The project data remains. "
            "You can redeploy with a new slug afterwards."
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        msg.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return

        api_key = self._get_api_key()

        def _run():
            try:
                api = WaystonesAPI(api_key)
                api.delete_deployment(deployment_id)
                self._log(f"Deployment {deployment_id} removed.")
                if self._selected_project:
                    self._project_fetched.emit(api.get_project(self._selected_project["id"]))
            except WaystonesAPIError as e:
                self._log(f"ERROR removing deployment: {e}")

        threading.Thread(target=_run, daemon=True).start()

    # ------------------------------------------------------------------
    # Tiles / STAC regeneration + polling
    # ------------------------------------------------------------------

    def _regen_worker(self, project_id: str, label: str, api_method: str, poll_fn):
        api_key = self._get_api_key()
        self._log(f"Queuing {label} regeneration for {project_id}…")
        def _run():
            try:
                getattr(WaystonesAPI(api_key), api_method)(project_id)
                self._log(f"{label} regeneration queued.")
                poll_fn(api_key, project_id)
            except WaystonesAPIError as e:
                self._log(f"ERROR queuing {label}: {e}")
        threading.Thread(target=_run, daemon=True).start()

    def _on_regen_tiles(self, project_id: str):
        self._regen_worker(project_id, "Tiles", "generate_tiles", self._poll_tiles_status)

    def _poll_tiles_status(self, api_key: str, project_id: str):
        """Background thread: poll tile job until done, forward worker log lines."""
        log_offset = 0
        for _ in range(120):  # up to ~6 minutes at 3 s intervals
            time.sleep(3)
            try:
                ts = WaystonesAPI(api_key).get_tiles_status(project_id)
            except Exception:
                break
            logs = ts.get("workerLog") or []
            for line in logs[log_offset:]:
                self._log(line)
            log_offset = len(logs)
            status = ts.get("status")
            if status == "success":
                self._log("✓ Tiles ready.")
                try:
                    project = WaystonesAPI(api_key).get_project(project_id)
                    self._project_fetched.emit(project)
                except Exception:
                    pass
                break
            if status and status not in ("running",):
                err = ts.get("errorMessage") or status
                self._log(f"✗ Tile generation failed: {err}")
                break

    def _poll_stac_status(self, api_key: str, project_id: str):
        """Background thread: poll STAC job until done, forward worker log lines."""
        log_offset = 0
        for _ in range(120):  # up to ~6 minutes at 3 s intervals
            time.sleep(3)
            try:
                ts = WaystonesAPI(api_key).get_stac_status(project_id)
            except Exception:
                break
            logs = ts.get("workerLog") or []
            for line in logs[log_offset:]:
                self._log(line)
            log_offset = len(logs)
            if ts.get("completed"):
                self._log("✓ STAC catalog ready.")
                try:
                    project = WaystonesAPI(api_key).get_project(project_id)
                    self._project_fetched.emit(project)
                except Exception:
                    pass
                break
            if not ts.get("active") and log_offset > 0:
                # worker finished but not marked completed — treat as done if we got logs
                self._log("✓ STAC generation finished.")
                break

    def _on_regen_stac(self, project_id: str):
        self._regen_worker(project_id, "STAC", "generate_stac", self._poll_stac_status)

    # ------------------------------------------------------------------
    # Metadata edit
    # ------------------------------------------------------------------

    def _show_metadata_edit(self, project: dict):
        dm = project.get("data_model") or {}
        meta = dm.get("metadata") or {}
        layers = dm.get("layers") or []

        w = QWidget()
        w.setStyleSheet("background: white;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        back_btn = QPushButton("← Back")
        back_btn.setObjectName("smallBtn")
        back_btn.clicked.connect(lambda: self._show_project_detail(project))
        layout.addWidget(back_btn)

        project_id = project["id"]

        title = QLabel("Edit Metadata")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #1e293b;")

        status_lbl = QLabel()
        status_lbl.setStyleSheet("font-size: 11px; color: #6366f1;")

        save_btn = QPushButton("Save Changes")
        save_btn.setObjectName("deployBtn")

        title_row = QHBoxLayout()
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(status_lbl)
        title_row.addWidget(save_btn)
        layout.addLayout(title_row)

        # ── Dataset metadata ───────────────────────────────────────────
        ds_hdr = QLabel("Dataset")
        ds_hdr.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #6366f1; text-transform: uppercase;"
            " letter-spacing: 1px; padding: 4px 0 2px 0; background: transparent;"
        )
        layout.addWidget(ds_hdr)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def _field(val=""):
            e = QLineEdit()
            e.setText(val or "")
            return e

        e_contact_name  = _field(meta.get("contactName"))
        e_contact_email = _field(meta.get("contactEmail"))
        e_contact_org   = _field(meta.get("contactOrganization"))
        e_keywords      = _field(", ".join(meta.get("keywords") or []))

        e_theme       = make_combo(THEMES, meta.get("theme"))
        e_license     = make_combo(LICENSES, meta.get("license"))
        e_access      = make_combo(ACCESS_RIGHTS, meta.get("accessRights"))
        e_periodicity = make_combo(PERIODICITIES, meta.get("accrualPeriodicity"))

        e_url           = _field(meta.get("url"))
        e_terms         = _field(meta.get("termsOfService"))

        e_purpose = QTextEdit()
        e_purpose.setPlainText(meta.get("purpose") or "")
        e_purpose.setMaximumHeight(80)

        form.addRow("Contact name:", e_contact_name)
        form.addRow("Email:", e_contact_email)
        form.addRow("Organization:", e_contact_org)
        form.addRow("Keywords:", e_keywords)
        form.addRow("Theme:", e_theme)
        form.addRow("License:", e_license)
        form.addRow("Access rights:", e_access)
        form.addRow("Purpose:", e_purpose)
        form.addRow("Update frequency:", e_periodicity)
        form.addRow("Dataset URL:", e_url)
        form.addRow("Terms:", e_terms)
        layout.addLayout(form)

        # ── Per-layer metadata ─────────────────────────────────────────
        layer_widgets: list[dict] = []
        if layers:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("color: #e2e8f0;")
            layout.addWidget(sep)

            lyr_hdr = QLabel("Layers")
            lyr_hdr.setStyleSheet(
                "font-size: 11px; font-weight: 700; color: #6366f1; text-transform: uppercase;"
                " letter-spacing: 1px; padding: 4px 0 2px 0; background: transparent;"
            )
            layout.addWidget(lyr_hdr)

            for lyr in layers:
                lyr_name = lyr.get("name") or lyr.get("id") or "Layer"
                geom_type = lyr.get("geometryType") or ""
                lyr_style = lyr.get("style") or {}
                lyr_meta = lyr.get("metadata") or {}

                card = QFrame()
                card.setStyleSheet(
                    "QFrame { border: 1px solid #e2e8f0; border-radius: 6px;"
                    " background: #f8fafc; padding: 0px; }"
                )
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(12, 10, 12, 10)
                card_layout.setSpacing(6)

                name_row = QHBoxLayout()
                name_lbl = QLabel(lyr_name)
                name_lbl.setStyleSheet("font-weight: 700; color: #1e293b; font-size: 12px; background: transparent;")
                geom_badge = QLabel(geom_type)
                geom_badge.setStyleSheet(
                    "font-size: 10px; color: #6366f1; background: #ede9fe;"
                    " border-radius: 4px; padding: 1px 6px;"
                )
                name_row.addWidget(name_lbl)
                name_row.addWidget(geom_badge)
                name_row.addStretch()
                card_layout.addLayout(name_row)

                lyr_form = QFormLayout()
                lyr_form.setSpacing(6)
                lyr_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

                e_lyr_title = _field(lyr.get("title"))
                e_lyr_desc = QTextEdit()
                e_lyr_desc.setPlainText(lyr.get("description") or "")
                e_lyr_desc.setMaximumHeight(52)
                e_lyr_kw = _field(", ".join(lyr_meta.get("keywords") or lyr.get("keywords") or []))

                color_hex = lyr_style.get("simpleColor") or "#6366f1"
                color_btn = QgsColorButton()
                color_btn.setColor(QColor(color_hex))
                color_btn.setMaximumWidth(80)

                lyr_form.addRow("Title:", e_lyr_title)
                lyr_form.addRow("Description:", e_lyr_desc)
                lyr_form.addRow("Keywords:", e_lyr_kw)
                lyr_form.addRow("Color:", color_btn)
                card_layout.addLayout(lyr_form)

                layout.addWidget(card)
                layer_widgets.append({
                    "layer": lyr,
                    "e_title": e_lyr_title,
                    "e_desc": e_lyr_desc,
                    "e_kw": e_lyr_kw,
                    "color_btn": color_btn,
                })

        def _is_valid_url(url: str) -> bool:
            try:
                p = urlparse(url)
                return p.scheme in ("http", "https") and bool(p.netloc)
            except Exception:
                return False

        # ── Wire save ──────────────────────────────────────────────────
        def _save():
            # Auto-update spatial extent from checked QGIS layers if available
            spatial_extent = meta.get("spatialExtent") or {}
            ext = self._checked_extent()
            if ext:
                spatial_extent = ext

            meta_url = e_url.text().strip()
            meta_terms = e_terms.text().strip()
            if meta_url and not _is_valid_url(meta_url):
                status_lbl.setText(f"Invalid Dataset URL")
                status_lbl.setStyleSheet("color: #dc2626; font-size: 11px;")
                return
            if meta_terms and not _is_valid_url(meta_terms):
                status_lbl.setText(f"Invalid Terms of Service URL")
                status_lbl.setStyleSheet("color: #dc2626; font-size: 11px;")
                return

            new_meta = {
                "contactName": e_contact_name.text().strip(),
                "contactEmail": e_contact_email.text().strip(),
                "contactOrganization": e_contact_org.text().strip(),
                "keywords": [k.strip() for k in e_keywords.text().split(",") if k.strip()],
                "theme": e_theme.currentData() or "",
                "license": e_license.currentData() or "",
                "accessRights": e_access.currentData() or "",
                "purpose": e_purpose.toPlainText().strip(),
                "accrualPeriodicity": e_periodicity.currentData() or "",
                "url": meta_url,
                "termsOfService": meta_terms,
                "spatialExtent": spatial_extent,
                "temporalExtentFrom": meta.get("temporalExtentFrom") or "",
                "temporalExtentTo": meta.get("temporalExtentTo") or "",
            }

            updated_layers = []
            for lw in layer_widgets:
                orig = lw["layer"]
                color = lw["color_btn"].color().name()
                kw_raw = lw["e_kw"].text()
                kw_list = [k.strip() for k in kw_raw.split(",") if k.strip()]
                updated_lyr = {
                    **orig,
                    "title": lw["e_title"].text().strip(),
                    "description": lw["e_desc"].toPlainText().strip(),
                    "keywords": kw_list,
                    "style": {**(orig.get("style") or {}), "simpleColor": color},
                }
                updated_layers.append(updated_lyr)

            base_layers = layers if not layer_widgets else updated_layers
            updated_dm = {**dm, "metadata": new_meta, "layers": base_layers}
            save_btn.setEnabled(False)
            status_lbl.setText("Saving…")
            status_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
            api_key = self._get_api_key()

            def _run():
                try:
                    api = WaystonesAPI(api_key)
                    api.update_project(project_id, data_model=updated_dm)
                    project["data_model"] = updated_dm
                    QTimer.singleShot(0, lambda: (
                        status_lbl.setText("✓ Metadata saved."),
                        status_lbl.setStyleSheet("color: #6366f1; font-size: 11px; font-weight: 600;"),
                    ))
                except WaystonesAPIError as e:
                    err = str(e)
                    QTimer.singleShot(0, lambda: (
                        status_lbl.setText(f"✗ {err}"),
                        status_lbl.setStyleSheet("color: #dc2626; font-size: 11px;"),
                    ))
                finally:
                    QTimer.singleShot(0, lambda: save_btn.setEnabled(True))

            threading.Thread(target=_run, daemon=True).start()

        save_btn.clicked.connect(_save)
        layout.addStretch()

        self._detail_scroll.setWidget(w)
