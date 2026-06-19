from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
    QStyle, QStyledItemDelegate, QVBoxLayout,
)
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtCore import Qt

from .options import DOMAINS, COMBO_VIEW_SS


class _IndigoItemDelegate(QStyledItemDelegate):
    """Custom item painter that gives combo popups indigo selection and hover colors.

    Necessary because Windows' native item-view renderer ignores QSS ::item:hover
    and draws hover state directly via the Windows API using the system accent color.
    """
    def paint(self, painter: QPainter, option, index):
        painter.save()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            painter.fillRect(option.rect, QColor("#6366f1"))
            painter.setPen(QColor("white"))
        elif hover:
            painter.fillRect(option.rect, QColor("#e0e7ff"))
            painter.setPen(QColor("#4338ca"))
        else:
            painter.fillRect(option.rect, QColor("white"))
            painter.setPen(QColor("#1e293b"))
        text = index.data()
        if text:
            painter.setFont(option.font)
            painter.drawText(
                option.rect.adjusted(8, 0, -4, 0),
                Qt.AlignmentFlag.AlignVCenter,
                text,
            )
        painter.restore()


def make_combo(options: list, current_val: str | None = None) -> QComboBox:
    cb = QComboBox()
    for val, label in options:
        cb.addItem(label, val)
    view = cb.view()
    view.setStyleSheet(COMBO_VIEW_SS)
    view.setItemDelegate(_IndigoItemDelegate(view))
    idx = cb.findData(current_val or "")
    if idx >= 0:
        cb.setCurrentIndex(idx)
    return cb


def make_domain_combo(current: str | None = None) -> QComboBox:
    cb = QComboBox()
    cb.setFixedWidth(88)
    for d in DOMAINS:
        cb.addItem(f".{d.split('.', 1)[1]}", d)
    view = cb.view()
    view.setStyleSheet(COMBO_VIEW_SS)
    view.setItemDelegate(_IndigoItemDelegate(view))
    if current:
        idx = cb.findData(current)
        if idx >= 0:
            cb.setCurrentIndex(idx)
    return cb


def card_frame() -> QFrame:
    f = QFrame()
    f.setStyleSheet("QFrame { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }")
    return f


def endpoint_frame(title: str):
    """Labelled section box for project-detail endpoint lists. Returns (frame, inner_layout)."""
    f = QFrame()
    f.setStyleSheet(
        "QFrame { background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 6px; }"
    )
    vb = QVBoxLayout(f)
    vb.setContentsMargins(10, 8, 10, 8)
    vb.setSpacing(4)
    t = QLabel(title)
    t.setStyleSheet(
        "font-size: 9px; font-weight: 700; color: #94a3b8;"
        " letter-spacing: 0.05em; background: transparent;"
    )
    vb.addWidget(t)
    return f, vb


def endpoint_row(layout, label_text: str, url: str, open_ext: bool = True):
    """One labelled URL row with a Copy button; appends to *layout*."""
    row = QHBoxLayout()
    row.setSpacing(6)
    name_lbl = QLabel(label_text + ":")
    name_lbl.setStyleSheet(
        "font-size: 10px; font-weight: 600; color: #64748b;"
        " min-width: 80px; background: transparent;"
    )
    if open_ext:
        url_text = QLabel(f'<a href="{url}" style="color:#6366f1; font-size:10px;">{url}</a>')
        url_text.setOpenExternalLinks(True)
    else:
        url_text = QLabel(url)
        url_text.setStyleSheet("font-size: 10px; color: #6366f1; background: transparent;")
    url_text.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse
    )
    copy_btn = QPushButton("Copy")
    copy_btn.setObjectName("smallBtn")
    copy_btn.setMaximumWidth(46)
    copy_btn.clicked.connect(lambda _=False, u=url: QApplication.clipboard().setText(u))
    row.addWidget(name_lbl)
    row.addWidget(url_text, 1)
    row.addWidget(copy_btn)
    layout.addLayout(row)
