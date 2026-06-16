import os
import re
import tempfile
import threading

from PyQt6.QtWidgets import (
    QButtonGroup, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QScrollArea, QWidget,
    QLineEdit, QPushButton, QCheckBox, QComboBox,
    QTextEdit, QProgressBar, QGroupBox, QSpinBox, QLabel,
    QMessageBox, QStackedWidget, QDoubleSpinBox, QFrame,
    QListWidget, QListWidgetItem,
)
from PyQt6.QtCore import QSettings, QTimer, pyqtSignal, Qt
from PyQt6.QtGui import QFont, QIcon, QPixmap
from qgis.gui import QgsRendererPropertiesDialog
from qgis.core import (
    QgsVectorFileWriter, QgsProject, QgsMapLayer,
    QgsWkbTypes, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsSingleSymbolRenderer, QgsCategorizedSymbolRenderer,
    QgsSimpleMarkerSymbolLayer, QgsSimpleLineSymbolLayer,
    QgsSimpleFillSymbolLayer, QgsLinePatternFillSymbolLayer,
    QgsVectorLayerSimpleLabeling, QgsStyle,
)

from .api import WaystonesAPI, WaystonesAPIError
from .options import THEMES, LICENSES, ACCESS_RIGHTS, PERIODICITIES
from .styles import QSS as _QSS, MSGBOX_QSS as _MSGBOX_QSS
from .widgets import make_combo, make_domain_combo
from .projects_panel import ProjectsPanel

SETTINGS_KEY_API_KEY = "waystones_cloud/api_key"
SETTINGS_KEY_IS_PRIVATE = "waystones_cloud/is_private"
SETTINGS_KEY_EU = "waystones_cloud/eu"
POLL_INTERVAL_MS = 5000
DEFAULT_COLOR = "#4A90D9"


class WaystonesDialog(QDialog):
    _log_line = pyqtSignal(str)
    _progress = pyqtSignal(int, int)
    _deploy_done = pyqtSignal(str)
    _deploy_error = pyqtSignal(str)
    _slug_result = pyqtSignal(str, str, bool)  # text, color, re-enable-btn

    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.setWindowTitle("Publish to Waystones Cloud")
        self.setMinimumWidth(900)
        self.setMinimumHeight(600)
        self._deployment_id = None
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_deployment)
        self._poll_log_offset = 0
        # {layer_id: {name, title, description, keywords, color}}
        self._layer_configs: dict = {}
        self._current_config_layer_id: str | None = None
        # replace-mode state
        self._replace_mode: bool = False
        self._replace_project_id: str | None = None
        self._replace_project: dict | None = None
        icon_path = os.path.join(os.path.dirname(__file__), "resources", "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self._build_ui()
        self._connect_signals()
        self._load_settings()
        self._populate_layer_list()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.setStyleSheet(_QSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── top: sidebar + pages ──────────────────────────────────
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(112)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(8, 16, 8, 12)
        sb.setSpacing(6)

        brand = QLabel("Waystones")
        brand.setStyleSheet(
            "color: #1e293b; font-size: 11px; font-weight: 700;"
            " padding: 0 4px 10px 4px; background: transparent;"
        )
        sb.addWidget(brand)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._nav_btns: list[QPushButton] = []

        def _nav_btn(label: str):
            btn = QPushButton(label)
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.setFlat(True)
            idx = len(self._nav_btns)
            self._nav_group.addButton(btn, idx)
            self._nav_btns.append(btn)
            sb.addWidget(btn)

        def _nav_sep():
            ln = QWidget()
            ln.setFixedHeight(1)
            ln.setStyleSheet("background-color: #e2e8f0;")
            sb.addWidget(ln)

        _nav_btn("Account")
        _nav_sep()
        for name in ("Source", "Metadata", "Layers", "Services"):
            _nav_btn(name)
        _nav_sep()
        _nav_btn("Projects")

        sb.addStretch(1)
        self._nav_btns[0].setChecked(True)

        top.addWidget(sidebar)

        self._pages = QStackedWidget()
        self._pages.addWidget(self._build_account_tab())
        self._pages.addWidget(self._build_source_tab())
        self._pages.addWidget(self._build_metadata_tab())
        self._pages.addWidget(self._build_layers_tab())
        self._pages.addWidget(self._build_services_tab())
        self._projects_panel = ProjectsPanel(
            get_api_key=lambda: self._api_key_edit.text().strip(),
            log=self._log_line.emit,
            request_replace=self._on_replace_gpkg,
            checked_extent=self._checked_layers_extent,
        )
        self._pages.addWidget(self._projects_panel)
        top.addWidget(self._pages, 1)

        root.addLayout(top, 1)

        # ── bottom: progress + log + buttons ─────────────────────
        bottom = QWidget()
        bottom.setObjectName("bottomBar")
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(12, 8, 12, 10)
        bl.setSpacing(6)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFixedHeight(5)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setVisible(False)
        bl.addWidget(self._progress_bar)

        self._log = QTextEdit()
        self._log.setObjectName("logArea")
        self._log.setReadOnly(True)
        self._log.setFixedHeight(90)
        mono = QFont("Courier New", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._log.setFont(mono)
        bl.addWidget(self._log)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._close_btn = QPushButton("Close")
        self._deploy_btn = QPushButton("Deploy")
        self._deploy_btn.setObjectName("deployBtn")
        self._deploy_btn.setDefault(True)
        btn_row.addStretch()
        btn_row.addWidget(self._close_btn)
        btn_row.addWidget(self._deploy_btn)
        bl.addLayout(btn_row)

        root.addWidget(bottom)

    def _build_account_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        header = QLabel("Account")
        header.setStyleSheet("font-size: 14px; font-weight: 700; color: #1e293b;")
        layout.addWidget(header)

        # Steps guide
        steps_frame = QFrame()
        steps_frame.setStyleSheet(
            "QFrame { background: #f0f0ff; border: 1px solid #c7d2fe; border-radius: 8px; }"
        )
        steps_layout = QVBoxLayout(steps_frame)
        steps_layout.setContentsMargins(14, 12, 14, 12)
        steps_layout.setSpacing(6)

        steps_title = QLabel("How to get your API key:")
        steps_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #4338ca; background: transparent;")
        steps_layout.addWidget(steps_title)

        for step in (
            "1.  Log in at  waystones.cloud",
            "2.  Open the  API  page from the sidebar",
            "3.  Click  Create API key  and copy it here",
        ):
            lbl = QLabel(step)
            lbl.setStyleSheet("font-size: 11px; color: #4338ca; background: transparent;")
            steps_layout.addWidget(lbl)

        layout.addWidget(steps_frame)

        # Key input row
        key_row = QHBoxLayout()
        key_row.setSpacing(8)

        self._api_key_edit = QLineEdit()
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setPlaceholderText("wsk_…")
        key_row.addWidget(self._api_key_edit, 1)

        self._verify_btn = QPushButton("Verify")
        self._verify_btn.setObjectName("smallBtn")
        self._verify_btn.setFixedWidth(68)
        key_row.addWidget(self._verify_btn)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.addRow("API key:", key_row)

        self._verify_status = QLabel()
        self._verify_status.setStyleSheet("font-size: 11px;")
        form.addRow("", self._verify_status)

        layout.addLayout(form)
        layout.addStretch()

        # Character lineup
        crew_frame = QFrame()
        crew_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        crew_layout = QVBoxLayout(crew_frame)
        crew_layout.setContentsMargins(0, 0, 0, 8)
        crew_layout.setSpacing(6)

        units_row = QHBoxLayout()
        units_row.setSpacing(4)
        units_row.addStretch()
        units_dir = os.path.join(os.path.dirname(__file__), "resources", "units")
        for unit in ("peon", "peasant", "wisp", "acolyte", "shade", "homunculus", "void-entity"):
            unit_path = os.path.join(units_dir, f"{unit}.png")
            if os.path.exists(unit_path):
                lbl = QLabel()
                pix = QPixmap(unit_path).scaled(
                    32, 32,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                lbl.setPixmap(pix)
                lbl.setToolTip(unit.replace("-", " ").title())
                units_row.addWidget(lbl)
        units_row.addStretch()
        crew_layout.addLayout(units_row)

        flavor = QLabel("Ready to carry your layers to the cloud. Paste your key and we'll find the way.")
        flavor.setStyleSheet("font-size: 10px; color: #94a3b8; font-style: italic;")
        flavor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        crew_layout.addWidget(flavor)

        layout.addWidget(crew_frame)

        note = QLabel('Lost your key? Visit <a href="https://waystones.cloud/api" style="color:#6366f1;">waystones.cloud/api</a>')
        note.setOpenExternalLinks(True)
        note.setStyleSheet("font-size: 11px; color: #6b7280;")
        layout.addWidget(note)

        return w

    def _build_source_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self._source_header = QLabel("Source")
        self._source_header.setStyleSheet("font-size: 14px; font-weight: 700; color: #1e293b;")
        layout.addWidget(self._source_header)

        # Replace-mode banner (hidden unless replacing an existing project)
        self._replace_banner = QFrame()
        self._replace_banner.setStyleSheet(
            "QFrame { background: #fef3c7; border: 1px solid #f59e0b; border-radius: 8px; }"
        )
        _banner_row = QHBoxLayout(self._replace_banner)
        _banner_row.setContentsMargins(12, 8, 12, 8)
        self._replace_banner_label = QLabel()
        self._replace_banner_label.setStyleSheet(
            "color: #92400e; font-size: 11px; font-weight: 600; background: transparent;"
        )
        _banner_row.addWidget(self._replace_banner_label, 1)
        _cancel_replace_btn = QPushButton("Cancel")
        _cancel_replace_btn.setObjectName("smallBtn")
        _cancel_replace_btn.setStyleSheet(
            "background: #fef3c7; border: 1px solid #f59e0b; color: #92400e;"
        )
        _cancel_replace_btn.clicked.connect(self._cancel_replace_mode)
        _banner_row.addWidget(_cancel_replace_btn)
        self._replace_banner.setVisible(False)
        layout.addWidget(self._replace_banner)

        layer_row = QHBoxLayout()
        layer_label = QLabel("Layers to publish:")
        layer_label.setStyleSheet("font-size: 11px; font-weight: 600; color: #6b7280; text-transform: uppercase;")
        layer_row.addWidget(layer_label)
        layer_row.addStretch()
        _refresh_layers_btn = QPushButton("↻  Refresh")
        _refresh_layers_btn.setObjectName("smallBtn")
        _refresh_layers_btn.clicked.connect(self._populate_layer_list)
        layer_row.addWidget(_refresh_layers_btn)
        layout.addLayout(layer_row)

        self._layer_list = QListWidget()
        self._layer_list.setObjectName("layerList")
        self._layer_list.setMinimumHeight(110)
        self._layer_list.setMaximumHeight(150)
        layout.addWidget(self._layer_list)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("My project")
        form.addRow("Project name: *", self._name_edit)

        slug_row = QHBoxLayout()
        slug_row.setSpacing(6)
        self._slug_edit = QLineEdit()
        self._slug_edit.setPlaceholderText("my-dataset")
        self._domain_combo = make_domain_combo()
        self._slug_check_btn = QPushButton("Check")
        self._slug_check_btn.setObjectName("smallBtn")
        self._slug_check_btn.setFixedWidth(60)
        self._slug_status_label = QLabel()
        self._slug_status_label.setStyleSheet("font-size: 11px;")
        slug_row.addWidget(self._slug_edit, 1)
        slug_row.addWidget(self._domain_combo)
        slug_row.addWidget(self._slug_check_btn)
        form.addRow("Slug: *", slug_row)
        form.addRow("", self._slug_status_label)

        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("Brief description of this dataset…")
        self._desc_edit.setMaximumHeight(56)
        form.addRow("Description:", self._desc_edit)

        self._chk_private = QCheckBox("Private (requires authentication to access)")
        form.addRow(self._chk_private)

        self._chk_eu = QCheckBox("Store data in EU jurisdiction")
        self._chk_eu.setToolTip(
            "Data is stored exclusively in EU data centres, satisfying GDPR and EU data\n"
            "residency requirements. Trade-off: disables the global edge network, so API\n"
            "responses may be slower for users outside the EU."
        )
        eu_note = QLabel("GDPR / data residency compliant · disables global edge network")
        eu_note.setStyleSheet("font-size: 10px; color: #94a3b8; padding-left: 22px; background: transparent;")
        form.addRow(self._chk_eu)
        form.addRow(eu_note)

        layout.addLayout(form)
        layout.addStretch()
        return w

    def _build_metadata_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        w = QWidget()
        w.setStyleSheet("background: white;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        header = QLabel("Metadata")
        header.setStyleSheet("font-size: 14px; font-weight: 700; color: #1e293b;")
        layout.addWidget(header)

        note = QLabel("Dataset-level metadata. Fields marked * are required.")
        note.setStyleSheet("font-size: 11px; color: #6b7280;")
        layout.addWidget(note)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._meta_contact_name = QLineEdit()
        form.addRow("Contact name: *", self._meta_contact_name)

        self._meta_contact_email = QLineEdit()
        self._meta_contact_email.setPlaceholderText("email@example.com")
        form.addRow("Contact email: *", self._meta_contact_email)

        self._meta_contact_org = QLineEdit()
        form.addRow("Organization: *", self._meta_contact_org)

        self._meta_keywords = QLineEdit()
        self._meta_keywords.setPlaceholderText("keyword1, keyword2, …")
        form.addRow("Keywords:", self._meta_keywords)

        self._meta_theme = make_combo(THEMES)
        form.addRow("Theme:", self._meta_theme)

        self._meta_license = make_combo(LICENSES)
        form.addRow("License:", self._meta_license)

        self._meta_access_rights = make_combo(ACCESS_RIGHTS)
        form.addRow("Access rights:", self._meta_access_rights)

        self._meta_purpose = QTextEdit()
        self._meta_purpose.setPlaceholderText("Purpose / intended use of this dataset…")
        self._meta_purpose.setMinimumHeight(80)
        self._meta_purpose.setMaximumHeight(120)
        form.addRow("Purpose:", self._meta_purpose)

        self._meta_periodicity = make_combo(PERIODICITIES)
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

        sep = QLabel("Spatial extent (WGS 84):")
        sep.setStyleSheet("font-size: 11px; font-weight: 600; color: #6b7280; padding-top: 4px;")
        form.addRow(sep)

        bbox_row1 = QHBoxLayout()
        bbox_row1.setSpacing(8)
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
        bbox_row2.setSpacing(8)
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

        self._bbox_detect_btn = QPushButton("Auto-detect from checked layers")
        self._bbox_detect_btn.setObjectName("smallBtn")
        form.addRow(self._bbox_detect_btn)

        layout.addLayout(form)
        scroll.setWidget(w)
        return scroll

    def _build_layers_tab(self):
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Left panel: layer selector
        left_panel = QFrame()
        left_panel.setObjectName("layersLeft")
        left_panel.setFixedWidth(160)
        left_panel.setStyleSheet("QFrame#layersLeft { background: #f8fafc; border-right: 1px solid #e2e8f0; }")
        left = QVBoxLayout(left_panel)
        left.setContentsMargins(10, 16, 10, 10)
        left.setSpacing(6)

        layer_hdr = QLabel("LAYERS")
        layer_hdr.setStyleSheet("font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.05em;")
        left.addWidget(layer_hdr)

        self._layer_config_list = QListWidget()
        self._layer_config_list.setObjectName("configList")
        left.addWidget(self._layer_config_list, 1)
        layout.addWidget(left_panel)

        # Right panel: per-layer config form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._layer_config_widget = QWidget()
        self._layer_config_widget.setStyleSheet("background: white;")
        form = QFormLayout(self._layer_config_widget)
        form.setContentsMargins(20, 16, 20, 16)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Fidelity info strip
        info_frame = QFrame()
        info_frame.setObjectName("styleInfoFrame")
        info_frame.setStyleSheet(
            "QFrame#styleInfoFrame { background: #f0f9ff; border: 1px solid #7dd3fc; border-radius: 6px; }"
        )
        info_l = QVBoxLayout(info_frame)
        info_l.setContentsMargins(10, 8, 10, 8)
        info_l.setSpacing(2)
        _info_title = QLabel("Style fidelity")
        _info_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #0c4a6e; background: transparent;")
        info_l.addWidget(_info_title)
        for _txt in (
            "✓  Carried over — single / categorized color, fill, line style, point icon, labels",
            "✗  Not carried over — rule-based, graduated, SVG markers, data-driven expressions",
            "⚠  Hatch patterns — WMS renders them; Vector Tiles show solid fill instead",
        ):
            _lbl = QLabel(_txt)
            _lbl.setWordWrap(True)
            _lbl.setStyleSheet("font-size: 10px; color: #0c4a6e; background: transparent;")
            info_l.addWidget(_lbl)
        form.addRow(info_frame)

        hint = QLabel("Check layers on the Source tab, then configure each one here.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #94a3b8; font-size: 11px;")
        form.addRow(hint)

        self._lyr_name_edit = QLineEdit()
        self._lyr_name_edit.setReadOnly(True)
        self._lyr_name_edit.setStyleSheet(
            "background: #f1f5f9; color: #64748b; border-color: #e2e8f0;"
        )
        form.addRow("Table name:", self._lyr_name_edit)

        self._lyr_title_edit = QLineEdit()
        form.addRow("Title:", self._lyr_title_edit)

        self._lyr_desc_edit = QTextEdit()
        self._lyr_desc_edit.setPlaceholderText("Description of this layer…")
        self._lyr_desc_edit.setMaximumHeight(70)
        form.addRow("Description:", self._lyr_desc_edit)

        self._lyr_keywords_edit = QLineEdit()
        self._lyr_keywords_edit.setPlaceholderText("keyword1, keyword2, …")
        form.addRow("Keywords:", self._lyr_keywords_edit)

        style_row = QHBoxLayout()
        style_row.setSpacing(8)
        self._lyr_color_swatch = QFrame()
        self._lyr_color_swatch.setFixedSize(22, 22)
        self._lyr_color_swatch.setStyleSheet(
            f"background: {DEFAULT_COLOR}; border: 1px solid #cbd5e1; border-radius: 3px;"
        )
        style_row.addWidget(self._lyr_color_swatch)
        self._lyr_edit_style_btn = QPushButton("Edit Style…")
        self._lyr_edit_style_btn.setObjectName("smallBtn")
        self._lyr_edit_style_btn.clicked.connect(self._open_style_editor)
        style_row.addWidget(self._lyr_edit_style_btn)
        style_row.addStretch()
        form.addRow("Style:", style_row)

        self._lyr_style_summary = QLabel()
        self._lyr_style_summary.setStyleSheet("font-size: 10px; color: #64748b;")
        form.addRow("", self._lyr_style_summary)

        self._layer_config_widget.setEnabled(False)
        scroll.setWidget(self._layer_config_widget)
        layout.addWidget(scroll, 1)

        return w

    def _build_services_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        header = QLabel("Services")
        header.setStyleSheet("font-size: 14px; font-weight: 700; color: #1e293b;")
        layout.addWidget(header)

        self._chk_oapif = QCheckBox("OGC API Features (OAPIF)")
        self._chk_oapif.setChecked(True)
        layout.addWidget(self._chk_oapif)

        self._chk_tiles = QCheckBox("Vector tiles")
        layout.addWidget(self._chk_tiles)

        self._tiles_options = QGroupBox()
        self._tiles_options.setFlat(True)
        tiles_form = QFormLayout(self._tiles_options)
        tiles_form.setContentsMargins(16, 4, 0, 4)
        tiles_form.setSpacing(6)

        self._chk_auto_zoom = QCheckBox("Auto zoom (recommended)")
        self._chk_auto_zoom.setChecked(True)
        tiles_form.addRow(self._chk_auto_zoom)

        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(6)
        self._spin_min_zoom = QSpinBox()
        self._spin_min_zoom.setRange(0, 14)
        self._spin_min_zoom.setValue(0)
        self._spin_min_zoom.setEnabled(False)
        self._spin_min_zoom.setFixedWidth(60)
        self._spin_max_zoom = QSpinBox()
        self._spin_max_zoom.setRange(0, 14)
        self._spin_max_zoom.setValue(14)
        self._spin_max_zoom.setEnabled(False)
        self._spin_max_zoom.setFixedWidth(60)
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
        self._spin_simplification.setFixedWidth(80)
        tiles_form.addRow("Tolerance:", self._spin_simplification)

        self._tiles_options.setVisible(False)
        layout.addWidget(self._tiles_options)

        self._chk_stac = QCheckBox("STAC catalog")
        layout.addWidget(self._chk_stac)

        self._stac_options = QGroupBox()
        self._stac_options.setFlat(True)
        stac_form = QFormLayout(self._stac_options)
        stac_form.setContentsMargins(16, 4, 0, 4)
        stac_form.setSpacing(6)

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

    def _on_replace_gpkg(self, project: dict):
        self._replace_mode = True
        self._replace_project_id = project["id"]
        self._replace_project = project
        self._replace_banner_label.setText(
            f"Replacing: {project.get('name', project['id'])}  —  "
            "select layers below, then click Replace."
        )
        self._replace_banner.setVisible(True)
        self._source_header.setText("Replace GPKG")
        self._deploy_btn.setText("Replace")
        self._on_nav_changed(1)  # Source tab

    def _cancel_replace_mode(self):
        self._replace_mode = False
        self._replace_project_id = None
        self._replace_project = None
        self._replace_banner.setVisible(False)
        self._source_header.setText("Source")
        self._deploy_btn.setText("Deploy")
        self._on_nav_changed(5)  # back to Projects

    # ------------------------------------------------------------------
    # Nav change handler
    # ------------------------------------------------------------------

    def _on_nav_changed(self, index: int):
        self._nav_btns[index].setChecked(True)
        self._pages.setCurrentIndex(index)
        is_projects = (index == 5)
        # The bottom-bar Deploy button drives the publish flow only; the Projects
        # tab has its own in-panel action buttons, so disable it there.
        if is_projects:
            self._deploy_btn.setEnabled(False)
            self._deploy_btn.setToolTip("Use the action buttons inside the project panel.")
            self._projects_panel.load_if_empty()
        else:
            self._deploy_btn.setEnabled(True)
            self._deploy_btn.setToolTip("")

    # ------------------------------------------------------------------
    # Layer list population and management
    # ------------------------------------------------------------------

    def _populate_layer_list(self):
        self._layer_list.blockSignals(True)
        self._layer_list.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() != QgsMapLayer.LayerType.VectorLayer:
                continue
            item = QListWidgetItem(layer.name())
            item.setData(Qt.ItemDataRole.UserRole, layer.id())
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._layer_list.addItem(item)
        self._layer_list.blockSignals(False)

    def _get_checked_layers(self):
        layers = []
        for i in range(self._layer_list.count()):
            item = self._layer_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                layer = QgsProject.instance().mapLayer(item.data(Qt.ItemDataRole.UserRole))
                if layer:
                    layers.append(layer)
        return layers

    def _on_layer_item_changed(self, item):
        layer_id = item.data(Qt.ItemDataRole.UserRole)
        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer:
            return

        if item.checkState() == Qt.CheckState.Checked:
            if layer_id not in self._layer_configs:
                self._layer_configs[layer_id] = {
                    "name": self._gpkg_table_name(layer),
                    "title": layer.name(),
                    "description": "",
                    "keywords": "",
                    "style": self._renderer_to_layer_style(layer),
                }
            cfg_item = QListWidgetItem(layer.name())
            cfg_item.setData(Qt.ItemDataRole.UserRole, layer_id)
            self._layer_config_list.addItem(cfg_item)

            # Auto-fill dataset name from the source GeoPackage on first layer
            if self._layer_config_list.count() == 1 and not self._name_edit.text():
                source = layer.source().split("|")[0]
                base = os.path.splitext(os.path.basename(source))[0] if source else layer.name()
                self._name_edit.setText(base)
                self._slug_edit.setText(re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-"))

            self._detect_bbox_from_layers()

        else:
            self._layer_configs.pop(layer_id, None)
            for i in range(self._layer_config_list.count()):
                cfg_item = self._layer_config_list.item(i)
                if cfg_item.data(Qt.ItemDataRole.UserRole) == layer_id:
                    self._layer_config_list.takeItem(i)
                    break
            if self._current_config_layer_id == layer_id:
                self._current_config_layer_id = None
                self._layer_config_widget.setEnabled(False)

    def _on_config_layer_selected(self, current, previous):
        # Persist edits for the layer we're leaving
        self._save_current_layer_config()

        if not current:
            self._layer_config_widget.setEnabled(False)
            self._current_config_layer_id = None
            return

        layer_id = current.data(Qt.ItemDataRole.UserRole)
        self._current_config_layer_id = layer_id
        cfg = self._layer_configs.get(layer_id, {})

        for widget in (self._lyr_name_edit, self._lyr_title_edit,
                        self._lyr_desc_edit, self._lyr_keywords_edit):
            widget.blockSignals(True)

        self._lyr_name_edit.setText(cfg.get("name", ""))
        self._lyr_title_edit.setText(cfg.get("title", ""))
        self._lyr_desc_edit.setPlainText(cfg.get("description", ""))
        self._lyr_keywords_edit.setText(cfg.get("keywords", ""))
        style = cfg.get("style", {})
        self._update_style_swatch(style.get("simpleColor", DEFAULT_COLOR))
        self._update_style_summary(style)

        for widget in (self._lyr_name_edit, self._lyr_title_edit,
                        self._lyr_desc_edit, self._lyr_keywords_edit):
            widget.blockSignals(False)

        self._layer_config_widget.setEnabled(True)

    def _save_current_layer_config(self):
        if not self._current_config_layer_id:
            return
        existing = self._layer_configs.get(self._current_config_layer_id, {})
        self._layer_configs[self._current_config_layer_id] = {
            "name": self._lyr_name_edit.text().strip(),
            "title": self._lyr_title_edit.text().strip(),
            "description": self._lyr_desc_edit.toPlainText().strip(),
            "keywords": self._lyr_keywords_edit.text().strip(),
            "style": existing.get("style", {"type": "simple", "simpleColor": DEFAULT_COLOR}),
        }

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self):
        self._nav_group.idClicked.connect(self._on_nav_changed)
        self._verify_btn.clicked.connect(self._verify_api_key)
        self._api_key_edit.textChanged.connect(lambda: self._verify_status.setText(""))
        self._deploy_btn.clicked.connect(self._on_deploy)
        self._close_btn.clicked.connect(self.close)
        self._layer_list.itemChanged.connect(self._on_layer_item_changed)
        self._layer_config_list.currentItemChanged.connect(self._on_config_layer_selected)
        self._slug_check_btn.clicked.connect(self._check_slug_availability)
        self._slug_edit.textChanged.connect(lambda: self._slug_status_label.setText(""))
        self._domain_combo.currentIndexChanged.connect(lambda: self._slug_status_label.setText(""))
        self._chk_tiles.toggled.connect(self._tiles_options.setVisible)
        self._chk_auto_zoom.toggled.connect(self._on_auto_zoom_toggled)
        self._chk_custom_simplification.toggled.connect(self._spin_simplification.setEnabled)
        self._chk_stac.toggled.connect(self._stac_options.setVisible)
        self._stac_partition_combo.currentIndexChanged.connect(self._on_partition_strategy_changed)
        self._bbox_detect_btn.clicked.connect(self._detect_bbox_from_layers)
        self._log_line.connect(self._append_log)
        self._progress.connect(self._update_progress)
        self._deploy_done.connect(self._on_deploy_done)
        self._deploy_error.connect(self._on_deploy_error)
        self._slug_result.connect(self._on_slug_result)

    def _on_auto_zoom_toggled(self, checked: bool):
        self._spin_min_zoom.setEnabled(not checked)
        self._spin_max_zoom.setEnabled(not checked)

    def _on_partition_strategy_changed(self):
        self._stac_partition_col.setEnabled(
            self._stac_partition_combo.currentData() == "custom_column"
        )

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------

    def _load_settings(self):
        s = QSettings()
        self._api_key_edit.setText(s.value(SETTINGS_KEY_API_KEY, ""))
        self._chk_eu.setChecked(s.value(SETTINGS_KEY_EU, "") == "eu")
        self._chk_private.setChecked(s.value(SETTINGS_KEY_IS_PRIVATE, False, type=bool))

    def _save_settings(self):
        s = QSettings()
        s.setValue(SETTINGS_KEY_API_KEY, self._api_key_edit.text().strip())
        s.setValue(SETTINGS_KEY_EU, "eu" if self._chk_eu.isChecked() else "default")
        s.setValue(SETTINGS_KEY_IS_PRIVATE, self._chk_private.isChecked())

    # ------------------------------------------------------------------
    # Bbox auto-detect
    # ------------------------------------------------------------------

    def _compute_wgs84_extent(self, layers):
        """Return (west, east, south, north) from combined WGS84 extents of *layers*, or None."""
        if not layers:
            return None
        try:
            west, east, south, north = 180.0, -180.0, 90.0, -90.0
            for layer in layers:
                ext = self._extent_wgs84(layer)
                west = min(west, ext.xMinimum())
                east = max(east, ext.xMaximum())
                south = min(south, ext.yMinimum())
                north = max(north, ext.yMaximum())
            return west, east, south, north
        except Exception:
            return None

    def _detect_bbox_from_layers(self):
        result = self._compute_wgs84_extent(self._get_checked_layers())
        if result:
            west, east, south, north = result
            self._bbox_west.setValue(west)
            self._bbox_east.setValue(east)
            self._bbox_south.setValue(south)
            self._bbox_north.setValue(north)

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

    def _checked_layers_extent(self):
        """Combined WGS84 extent of the checked layers as a dict, or None."""
        result = self._compute_wgs84_extent(self._get_checked_layers())
        if result:
            west, east, south, north = result
            return {"west": west, "east": east, "south": south, "north": north}
        return None

    def _open_style_editor(self):
        if not self._current_config_layer_id:
            return
        layer = QgsProject.instance().mapLayer(self._current_config_layer_id)
        if not layer:
            return
        dlg = QgsRendererPropertiesDialog(layer, QgsStyle.defaultStyle(), False, self)
        if dlg.exec():
            style = self._renderer_to_layer_style(layer)
            cfg = self._layer_configs.get(self._current_config_layer_id, {})
            cfg["style"] = style
            self._layer_configs[self._current_config_layer_id] = cfg
            self._update_style_swatch(style.get("simpleColor", DEFAULT_COLOR))
            self._update_style_summary(style)

    def _renderer_to_layer_style(self, layer) -> dict:
        """Translate the layer's current QGIS renderer into a LayerStyle dict."""
        style: dict = {"type": "simple", "simpleColor": DEFAULT_COLOR}

        try:
            renderer = layer.renderer()
            if not renderer:
                return style

            _pen_dash = {
                "solidline": "solid", "dashline": "dashed", "dotline": "dotted",
                "dashdotline": "dash-dot", "dashdotdotline": "dash-dot-dot",
            }
            _brush_hatch = {
                "horpattern": "horizontal", "verpattern": "vertical",
                "crosspattern": "cross", "bdiagpattern": "b_diagonal",
                "fdiagpattern": "f_diagonal", "diagcrosspattern": "diagonal_x",
            }

            if isinstance(renderer, QgsSingleSymbolRenderer):
                sym = renderer.symbol()
                style["simpleColor"] = sym.color().name()
                opacity = sym.opacity()

                for i in range(sym.symbolLayerCount()):
                    sl = sym.symbolLayer(i)

                    if isinstance(sl, QgsSimpleMarkerSymbolLayer):
                        style["pointOpacity"] = opacity
                        style["pointSize"] = sl.size()
                        shape_name = sl.shape().name.lower()
                        if "square" in shape_name or "rectangle" in shape_name:
                            style["pointIcon"] = "square"
                        elif "triangle" in shape_name:
                            style["pointIcon"] = "triangle"
                        elif "star" in shape_name:
                            style["pointIcon"] = "star"
                        else:
                            style["pointIcon"] = "circle"
                        break

                    elif isinstance(sl, QgsSimpleLineSymbolLayer):
                        style["lineOpacity"] = opacity
                        style["lineWidth"] = sl.width()
                        style["lineDash"] = _pen_dash.get(sl.penStyle().name.lower(), "solid")
                        break

                    elif isinstance(sl, QgsSimpleFillSymbolLayer):
                        style["fillOpacity"] = opacity
                        stroke = sl.strokeStyle()
                        style["showOutline"] = stroke.name.lower() != "nopen"
                        if style["showOutline"]:
                            style["lineWidth"] = sl.strokeWidth()
                            style["lineDash"] = _pen_dash.get(stroke.name.lower(), "solid")
                        hatch = _brush_hatch.get(sl.brushStyle().name.lower())
                        if hatch:
                            style["hatchStyle"] = hatch
                        break

                    elif isinstance(sl, QgsLinePatternFillSymbolLayer):
                        style["fillOpacity"] = opacity
                        style["hatchSpacing"] = sl.distance()
                        angle = sl.lineAngle() % 180
                        if angle < 5:
                            style["hatchStyle"] = "horizontal"
                        elif abs(angle - 90) < 5:
                            style["hatchStyle"] = "vertical"
                        elif abs(angle - 45) < 5:
                            style["hatchStyle"] = "b_diagonal"
                        else:
                            style["hatchStyle"] = "f_diagonal"
                        break

            elif isinstance(renderer, QgsCategorizedSymbolRenderer):
                style["type"] = "categorized"
                style["propertyId"] = renderer.classAttribute()
                cat_settings: dict = {}
                cat_values: list = []
                fallback_color = DEFAULT_COLOR

                for cat in renderer.categories():
                    val = str(cat.value())
                    sym = cat.symbol()
                    if not val:
                        if sym:
                            fallback_color = sym.color().name()
                        continue
                    cat_values.append(val)
                    entry: dict = {}
                    if sym:
                        entry["color"] = sym.color().name()
                        opacity = sym.opacity()
                        for i in range(sym.symbolLayerCount()):
                            sl = sym.symbolLayer(i)
                            if isinstance(sl, QgsSimpleMarkerSymbolLayer):
                                entry["pointSize"] = sl.size()
                                entry["pointOpacity"] = opacity
                            elif isinstance(sl, QgsSimpleLineSymbolLayer):
                                entry["lineWidth"] = sl.width()
                                entry["lineOpacity"] = opacity
                            elif isinstance(sl, QgsSimpleFillSymbolLayer):
                                entry["fillOpacity"] = opacity
                            break
                    cat_settings[val] = entry

                style["simpleColor"] = fallback_color
                style["categorizedSettings"] = cat_settings
                style["categorizedValues"] = cat_values

            else:
                # Graduated, rule-based, etc. — grab primary color only
                try:
                    style["simpleColor"] = renderer.symbol().color().name()
                except Exception:
                    pass

        except Exception:
            pass

        # Labels
        try:
            labeling = layer.labeling()
            if labeling and isinstance(labeling, QgsVectorLayerSimpleLabeling):
                settings = labeling.settings()
                if not settings.isExpression and settings.fieldName:
                    fmt = settings.format()
                    style["labelSettings"] = {
                        "enabled": True,
                        "propertyId": settings.fieldName,
                        "fontSize": int(fmt.size()),
                        "color": fmt.color().name(),
                        "fontFamily": fmt.font().family(),
                        "haloEnabled": fmt.buffer().enabled(),
                        "haloSize": fmt.buffer().size(),
                        "haloColor": fmt.buffer().color().name(),
                    }
        except Exception:
            pass

        return style

    def _update_style_swatch(self, color_hex: str):
        self._lyr_color_swatch.setStyleSheet(
            f"background: {color_hex}; border: 1px solid #cbd5e1; border-radius: 3px;"
        )

    def _update_style_summary(self, style: dict):
        kind = style.get("type", "simple")
        if kind == "categorized":
            prop = style.get("propertyId", "")
            n = len(style.get("categorizedValues") or style.get("categorizedSettings") or [])
            self._lyr_style_summary.setText(f"Categorized by: {prop}  ·  {n} value(s)")
        elif style.get("hatchStyle") and style["hatchStyle"] != "solid":
            self._lyr_style_summary.setText(f"Hatch: {style['hatchStyle']}  ·  WMS only")
        elif style.get("labelSettings", {}).get("enabled"):
            field = style["labelSettings"].get("propertyId", "")
            self._lyr_style_summary.setText(f"Labels: {field}")
        else:
            self._lyr_style_summary.setText("")

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

    def _table_name(self, name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:63]

    def _gpkg_table_name(self, layer) -> str:
        """Return the actual table name from the layer's GeoPackage source, or fall back to sanitized display name."""
        source = layer.source()
        if "|layername=" in source:
            return source.split("|layername=")[1].split("|")[0]
        return self._table_name(layer.name())

    def _geometry_type_str(self, layer):
        flat = QgsWkbTypes.flatType(layer.wkbType())
        return {
            QgsWkbTypes.Type.Point: "Point",
            QgsWkbTypes.Type.MultiPoint: "MultiPoint",
            QgsWkbTypes.Type.LineString: "LineString",
            QgsWkbTypes.Type.MultiLineString: "MultiLineString",
            QgsWkbTypes.Type.Polygon: "Polygon",
            QgsWkbTypes.Type.MultiPolygon: "MultiPolygon",
            QgsWkbTypes.Type.GeometryCollection: "GeometryCollection",
            QgsWkbTypes.Type.NoGeometry: "None",
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
        return [
            {
                "id": qf.name(),
                "name": qf.name(),
                "title": qf.alias() or qf.name(),
                "description": "",
                "multiplicity": "0..1",
                "fieldType": {"kind": "primitive", "baseType": self._field_base_type(qf)},
            }
            for qf in layer.fields()
            if qf.name().lower() not in skip
        ]

    def _build_data_model(self, layers, name, description):
        self._save_current_layer_config()

        bbox = self._compute_wgs84_extent(layers)
        if bbox:
            west, east, south, north = bbox
            spatial_extent = {
                "westBoundLongitude": str(round(west, 6)),
                "eastBoundLongitude": str(round(east, 6)),
                "southBoundLatitude": str(round(south, 6)),
                "northBoundLatitude": str(round(north, 6)),
            }
        else:
            spatial_extent = {
                "westBoundLongitude": str(self._bbox_west.value()),
                "eastBoundLongitude": str(self._bbox_east.value()),
                "southBoundLatitude": str(self._bbox_south.value()),
                "northBoundLatitude": str(self._bbox_north.value()),
            }

        crs = layers[0].crs().authid() if layers else "EPSG:4326"

        layer_objs = []
        for layer in layers:
            cfg = self._layer_configs.get(layer.id(), {})
            table_id = cfg.get("name") or self._gpkg_table_name(layer)
            layer_objs.append({
                "id": table_id,
                "name": cfg.get("name") or layer.name(),
                "title": cfg.get("title") or layer.name(),
                "description": cfg.get("description", ""),
                "keywords": [k.strip() for k in cfg.get("keywords", "").split(",") if k.strip()],
                "geometryType": self._geometry_type_str(layer),
                "geometryColumnName": "geom",
                "primaryKeyColumn": "fid",
                "properties": self._extract_fields(layer),
                "style": cfg.get("style") or {"type": "simple", "simpleColor": DEFAULT_COLOR},
            })

        keywords = [k.strip() for k in self._meta_keywords.text().split(",") if k.strip()]

        return {
            "name": name,
            "namespace": re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"),
            "description": description,
            "version": "1.0.0",
            "crs": crs,
            "layers": layer_objs,
            "metadata": {
                "contactName": self._meta_contact_name.text().strip(),
                "contactEmail": self._meta_contact_email.text().strip(),
                "contactOrganization": self._meta_contact_org.text().strip(),
                "keywords": keywords,
                "theme": self._meta_theme.currentData() or "",
                "license": self._meta_license.currentData() or "",
                "accessRights": self._meta_access_rights.currentData() or "",
                "purpose": self._meta_purpose.toPlainText().strip(),
                "accrualPeriodicity": self._meta_periodicity.currentData() or "",
                "temporalExtentFrom": self._meta_temporal_from.text().strip(),
                "temporalExtentTo": self._meta_temporal_to.text().strip(),
                "url": self._meta_url.text().strip(),
                "termsOfService": self._meta_terms.text().strip(),
                "spatialExtent": spatial_extent,
            },
        }

    # ------------------------------------------------------------------
    # API key verification
    # ------------------------------------------------------------------

    def _verify_api_key(self):
        api_key = self._api_key_edit.text().strip()
        if not api_key:
            self._verify_status.setText("Enter an API key first.")
            self._verify_status.setStyleSheet("color: #6b7280; font-size: 11px;")
            return
        self._verify_btn.setEnabled(False)
        self._verify_status.setText("Checking…")
        self._verify_status.setStyleSheet("color: #94a3b8; font-size: 11px;")

        def _check():
            try:
                api = WaystonesAPI(api_key)
                projects = api.verify_key()
                n = len(projects) if isinstance(projects, list) else "?"
                self._save_settings()
                QTimer.singleShot(0, lambda: (
                    self._verify_status.setText(f"✓ Authenticated  —  {n} project(s) on this account"),
                    self._verify_status.setStyleSheet("color: #6366f1; font-size: 11px; font-weight: 600;"),
                ))
            except WaystonesAPIError as e:
                msg = str(e)
                text = "✗ Invalid key — check and try again" if "401" in msg else f"✗ {msg}"
                QTimer.singleShot(0, lambda: (
                    self._verify_status.setText(text),
                    self._verify_status.setStyleSheet("color: #dc2626; font-size: 11px; font-weight: 600;"),
                ))
            finally:
                QTimer.singleShot(0, lambda: self._verify_btn.setEnabled(True))

        threading.Thread(target=_check, daemon=True).start()

    # ------------------------------------------------------------------
    # Slug availability check
    # ------------------------------------------------------------------

    def _check_slug_availability(self):
        api_key = self._api_key_edit.text().strip()
        slug = self._slug_edit.text().strip()
        domain = self._domain_combo.currentData()
        if not api_key or not slug:
            self._slug_status_label.setText("Enter API key and slug first.")
            return
        self._slug_check_btn.setEnabled(False)
        self._slug_status_label.setText("Checking…")
        self._slug_status_label.setStyleSheet("color: #94a3b8; font-size: 11px;")

        def _check():
            try:
                api = WaystonesAPI(api_key)
                result = api.check_slug(slug, domain)
                if result.get("available"):
                    self._slug_result.emit(f"✓ Available on {domain}", "#6366f1", True)
                else:
                    self._slug_result.emit(f"✗ {result.get('error', 'Not available.')}", "#dc2626", True)
            except Exception as e:
                self._slug_result.emit(f"Error: {e}", "#dc2626", True)

        threading.Thread(target=_check, daemon=True).start()

    # ------------------------------------------------------------------
    # Deploy
    # ------------------------------------------------------------------

    def _on_deploy(self):
        if self._replace_mode:
            self._on_replace_submit()
            return

        api_key = self._api_key_edit.text().strip()
        if not api_key:
            self._warn("Please enter your API key.")
            return

        layers = self._get_checked_layers()
        if not layers:
            self._warn("Check at least one layer on the Source tab.")
            return

        name = self._name_edit.text().strip()
        if not name:
            self._warn("Please enter a dataset name.")
            return

        slug = self._slug_edit.text().strip()
        if not slug:
            self._warn("Please enter a slug.")
            return

        services = ["oapif"] if self._chk_oapif.isChecked() else []
        generate_tiles = self._chk_tiles.isChecked()
        generate_stac = self._chk_stac.isChecked()

        if not services and not generate_tiles and not generate_stac:
            self._warn("Select at least one service.")
            return

        auto_zoom = self._chk_auto_zoom.isChecked()
        min_zoom = self._spin_min_zoom.value()
        max_zoom = self._spin_max_zoom.value()
        if not auto_zoom and min_zoom > max_zoom:
            self._warn("Min zoom must be ≤ max zoom.")
            return

        simplification = (
            self._spin_simplification.value()
            if self._chk_custom_simplification.isChecked() else None
        )
        partition_strategy = None
        partition_column = None
        if generate_stac:
            partition_strategy = self._stac_partition_combo.currentData()
            if partition_strategy == "custom_column":
                partition_column = self._stac_partition_col.text().strip() or None

        data_model = self._build_data_model(layers, name, self._desc_edit.toPlainText().strip())

        self._save_settings()
        self._set_busy(True)
        self._log.clear()
        self._poll_log_offset = 0

        threading.Thread(
            target=self._run_deploy,
            args=(
                api_key, layers, slug, self._domain_combo.currentData(), services,
                generate_tiles, generate_stac,
                auto_zoom, min_zoom, max_zoom, simplification,
                "eu" if self._chk_eu.isChecked() else "default",
                self._chk_private.isChecked(),
                data_model, partition_strategy, partition_column,
            ),
            daemon=True,
        ).start()

    def _on_replace_submit(self):
        api_key = self._api_key_edit.text().strip()
        if not api_key:
            self._warn("Please enter your API key.")
            return
        layers = self._get_checked_layers()
        if not layers:
            self._warn("Check at least one layer on the Source tab.")
            return
        project = self._replace_project
        data_model = self._build_data_model(
            layers,
            project.get("name", ""),
            (project.get("data_model") or {}).get("description", ""),
        )
        self._set_busy(True)
        self._log.clear()
        self._poll_log_offset = 0
        threading.Thread(
            target=self._run_replace,
            args=(api_key, layers, self._replace_project_id, data_model),
            daemon=True,
        ).start()

    def _export_and_upload(self, api, layers, slug, **url_kwargs):
        """Export layers to a temp GPKG, upload it, and return (object_key, file_size)."""
        tmp_dir = tempfile.mkdtemp()
        gpkg_path = os.path.join(tmp_dir, f"{slug}.gpkg")
        try:
            self._log_line.emit(f"Exporting {len(layers)} layer(s) to GeoPackage…")
            self._export_layers(layers, gpkg_path)
            file_size = os.path.getsize(gpkg_path)
            self._log_line.emit(f"Exported: {file_size // 1024} KB")

            self._log_line.emit("Requesting upload URL…")
            upload_info = api.get_upload_url(filename=os.path.basename(gpkg_path), **url_kwargs)
            presigned_url = upload_info["presignedUrl"]
            object_key = upload_info["objectKey"]

            self._log_line.emit("Uploading…")
            api.upload_file(presigned_url, gpkg_path,
                            progress_callback=lambda d, t: self._progress.emit(d, t))
            self._log_line.emit("Upload complete.")
            return object_key, file_size
        finally:
            try:
                os.remove(gpkg_path)
                os.rmdir(tmp_dir)
            except Exception:
                pass

    def _run_replace(self, api_key: str, layers: list, project_id: str, data_model: dict):
        try:
            api = WaystonesAPI(api_key)
            slug = re.sub(r"[^a-z0-9]+", "-", data_model.get("name", project_id).lower()).strip("-")
            object_key, file_size = self._export_and_upload(api, layers, slug)
            self._log_line.emit("Replacing project file…")
            api.replace_project_file(project_id, object_key, file_size)
            self._log_line.emit("Updating data model…")
            api.update_project(project_id, data_model=data_model)
            self._deploy_done.emit("")
        except (WaystonesAPIError, Exception) as e:
            self._deploy_error.emit(f"Replace failed: {e}")

    def _run_deploy(
        self, api_key, layers, slug, domain, services,
        generate_tiles, generate_stac,
        auto_zoom, min_zoom, max_zoom, simplification,
        data_region, is_private,
        data_model, partition_strategy, partition_column,
    ):
        try:
            api = WaystonesAPI(api_key)
            object_key, file_size = self._export_and_upload(
                api, layers, slug,
                is_private=is_private, data_region=data_region,
            )

            self._log_line.emit("Creating project…")
            project = api.create_project(
                name=data_model["name"],
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
                deploy_result = api.deploy(project_id, slug, services, domain=domain)
                self._deployment_id = deploy_result["deploymentId"]
                self._log_line.emit(f"Deployment queued: {self._deployment_id}")
                QTimer.singleShot(0, self._start_poll)
            else:
                self._deploy_done.emit("")

        except WaystonesAPIError as e:
            self._deploy_error.emit(str(e))
        except Exception as e:
            self._deploy_error.emit(f"Unexpected error: {e}")

    def _export_layers(self, layers, dest_path):
        for i, layer in enumerate(layers):
            cfg = self._layer_configs.get(layer.id(), {})
            table_name = cfg.get("name") or self._gpkg_table_name(layer)
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "GPKG"
            options.fileEncoding = "UTF-8"
            options.layerName = table_name
            if i > 0:
                options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
            error, msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
                layer, dest_path, QgsProject.instance().transformContext(), options
            )
            if error != QgsVectorFileWriter.WriterError.NoError:
                raise RuntimeError(f"Export failed for '{layer.name()}': {msg}")

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

    def _warn(self, text: str):
        msg = QMessageBox(self)
        msg.setWindowTitle("Waystones Cloud")
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setStyleSheet(_MSGBOX_QSS)
        msg.setText(text)
        msg.exec()

    def closeEvent(self, event):
        self._save_settings()
        super().closeEvent(event)

    def _set_busy(self, busy: bool):
        self._deploy_btn.setEnabled(not busy)
        self._progress_bar.setVisible(busy)
        if not busy:
            self._progress_bar.setValue(0)

    def _append_log(self, text: str):
        upper = text.upper()
        if "ERROR" in upper or "FAIL" in upper or "CRITICAL" in upper:
            color = "#fb7185"  # rose-400
        elif "WARN" in upper:
            color = "#fbbf24"  # amber-400
        else:
            color = "#a78bfa"  # violet-400
        self._log.append(f'<span style="color:{color}; font-family: monospace;">{text}</span>')

    def _update_progress(self, done: int, total: int):
        if total > 0:
            self._progress_bar.setValue(int(done / total * 100))

    def _on_deploy_done(self, public_url: str):
        self._set_busy(False)
        if self._replace_mode:
            self._cancel_replace_mode()
            self._projects_panel.load_projects()
        msg = QMessageBox(self)
        msg.setWindowTitle("Waystones Cloud")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setStyleSheet(_MSGBOX_QSS)
        if public_url:
            msg.setText("Deployment is live!")
            msg.setInformativeText(
                f'<a href="{public_url}" style="color:#6366f1;">{public_url}</a>'
            )
            msg.setTextFormat(Qt.TextFormat.RichText)
        else:
            msg.setText("Deployment is live!")
        msg.exec()

    def _on_slug_result(self, text: str, color: str, re_enable: bool):
        self._slug_status_label.setText(text)
        self._slug_status_label.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 600;")
        if re_enable:
            self._slug_check_btn.setEnabled(True)

    def _on_deploy_error(self, message: str):
        self._poll_timer.stop()
        self._set_busy(False)
        self._append_log(f"ERROR: {message}")
        short = re.sub(r"https?://\S+", "<URL redacted>", message)
        short = short.split("(Caused by")[0].strip()
        if len(short) > 300:
            short = short[:300] + "…"
        msg = QMessageBox(self)
        msg.setWindowTitle("Waystones Cloud")
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setStyleSheet(_MSGBOX_QSS)
        msg.setText(short)
        msg.setInformativeText("See the log area below for full details.")
        msg.exec()
