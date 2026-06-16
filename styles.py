QSS = """
/* ── Dialog background ─────────────────────────────────────────── */
WaystonesDialog {
    background: #f8fafc;
}

/* ── Sidebar ────────────────────────────────────────────────────── */
QFrame#sidebar {
    background: #f8fafc;
    border-right: 1px solid #e2e8f0;
}

QPushButton#navBtn {
    background: transparent;
    border: none;
    border-radius: 6px;
    color: #64748b;
    font-size: 11px;
    font-weight: 600;
    padding: 7px 10px;
    text-align: left;
}
QPushButton#navBtn:hover {
    background: #f1f5f9;
    color: #374151;
}
QPushButton#navBtn:checked {
    background: #e0e7ff;
    color: #4338ca;
}

/* ── Content pages ──────────────────────────────────────────────── */
QStackedWidget {
    background: white;
}

/* ── Form inputs ────────────────────────────────────────────────── */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 5px 8px;
    color: #1e293b;
    font-size: 12px;
    min-height: 22px;
    selection-background-color: #6366f1;
}
QLineEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #6366f1;
}
QTextEdit {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 5px 8px;
    color: #1e293b;
    font-size: 12px;
    selection-background-color: #6366f1;
}
QTextEdit:focus {
    border-color: #6366f1;
}

/* ── Spinbox arrows ─────────────────────────────────────────────── */
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    border: none;
    background: transparent;
    width: 16px;
}

/* ── Combo drop-down ────────────────────────────────────────────── */
QComboBox::drop-down {
    border: none;
    padding-right: 6px;
}
QComboBox QAbstractItemView {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    selection-background-color: #6366f1;
    selection-color: white;
    outline: none;
}

/* ── Labels ─────────────────────────────────────────────────────── */
QLabel {
    color: #374151;
    font-size: 12px;
    background: transparent;
}

/* ── Checkboxes ─────────────────────────────────────────────────── */
QCheckBox {
    color: #374151;
    font-size: 12px;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #cbd5e1;
    border-radius: 3px;
    background: white;
}
QCheckBox::indicator:checked {
    background: #6366f1;
    border-color: #6366f1;
}

/* ── Layer list (Source tab) ────────────────────────────────────── */
QListWidget#layerList {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    color: #1e293b;
    font-size: 12px;
    outline: none;
}
QListWidget#layerList::item:selected {
    background: #e0e7ff;
    color: #3730a3;
}
QListWidget#layerList::indicator:unchecked {
    border: 1px solid #cbd5e1;
    border-radius: 3px;
    background: white;
    width: 13px;
    height: 13px;
}
QListWidget#layerList::indicator:checked {
    border: 1px solid #6366f1;
    border-radius: 3px;
    background: #6366f1;
    width: 13px;
    height: 13px;
}

/* ── Layer config list (Layers tab) ─────────────────────────────── */
QListWidget#configList {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    color: #1e293b;
    font-size: 11px;
    outline: none;
}
QListWidget#configList::item:selected {
    background: #e0e7ff;
    color: #3730a3;
}

/* ── Buttons ────────────────────────────────────────────────────── */
QPushButton {
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    color: #374151;
    font-size: 12px;
    font-weight: 600;
    padding: 6px 14px;
}
QPushButton:hover {
    background: #e2e8f0;
    border-color: #cbd5e1;
}
QPushButton:pressed {
    background: #cbd5e1;
}
QPushButton#deployBtn {
    background: #6366f1;
    border: none;
    color: white;
    padding: 7px 20px;
}
QPushButton#deployBtn:hover {
    background: #4f46e5;
}
QPushButton#deployBtn:disabled {
    background: #a5b4fc;
}
QPushButton#smallBtn {
    padding: 4px 10px;
    font-size: 11px;
}
QPushButton#dangerBtn {
    background: white;
    border: 1px solid #fca5a5;
    color: #dc2626;
    padding: 4px 10px;
    font-size: 11px;
}
QPushButton#dangerBtn:hover {
    background: #fee2e2;
    border-color: #f87171;
}
QPushButton#dangerBtn:pressed {
    background: #fecaca;
}

/* ── Progress bar ───────────────────────────────────────────────── */
QProgressBar {
    border: none;
    border-radius: 3px;
    background: #e2e8f0;
    text-align: center;
}
QProgressBar::chunk {
    background: #6366f1;
    border-radius: 3px;
}

/* ── Log area ───────────────────────────────────────────────────── */
QTextEdit#logArea {
    background: #020617;
    color: #a78bfa;
    border: none;
    border-radius: 8px;
    font-size: 12px;
    padding: 6px;
}

/* ── Projects list ──────────────────────────────────────────────── */
QListWidget#projectsList {
    border: none;
    border-right: 1px solid #e2e8f0;
    background: #f8fafc;
    color: #1e293b;
    font-size: 12px;
    outline: none;
}
QListWidget#projectsList::item {
    padding: 10px 14px;
    border-bottom: 1px solid #f1f5f9;
}
QListWidget#projectsList::item:selected {
    background: #e0e7ff;
    color: #3730a3;
}

/* ── Bottom bar ─────────────────────────────────────────────────── */
QWidget#bottomBar {
    background: #f8fafc;
    border-top: 1px solid #e2e8f0;
}

/* ── GroupBox ───────────────────────────────────────────────────── */
QGroupBox {
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    margin-top: 6px;
    padding-top: 2px;
    color: #374151;
    font-weight: 600;
    font-size: 11px;
    background: transparent;
}

/* ── Scroll bars ────────────────────────────────────────────────── */
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    width: 6px;
    background: transparent;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #cbd5e1;
    border-radius: 3px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { height: 6px; background: transparent; }
QScrollBar::handle:horizontal {
    background: #cbd5e1;
    border-radius: 3px;
    min-width: 20px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
"""

MSGBOX_QSS = """
QMessageBox {
    background: white;
}
QMessageBox QLabel {
    color: #1e293b;
    font-size: 12px;
    background: transparent;
}
QMessageBox QPushButton {
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    color: #374151;
    font-size: 12px;
    font-weight: 600;
    padding: 5px 16px;
    min-width: 64px;
}
QMessageBox QPushButton:default {
    background: #6366f1;
    border: none;
    color: white;
}
QMessageBox QPushButton:hover {
    background: #e2e8f0;
}
QMessageBox QPushButton:default:hover {
    background: #4f46e5;
}
"""
