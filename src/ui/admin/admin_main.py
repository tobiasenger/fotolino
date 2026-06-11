"""
Admin container screen (PyQt6).
Vertical sidebar (header, tab buttons, Schließen at the bottom) and a
QStackedWidget for content. Tabs: Szenen | Pfade | Einstellungen –
scenes first, because paths are built from scenes.

The whole admin area is styled by ONE swappable QSS file
(assets/themes/admin_dark.qss, see ADMIN_DESIGN.md). This module only sets
object names / "kind" properties; it contains no visual styling itself.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import theme
from ..base_screen import BaseScreen
from ..widgets import make_separator, set_kind
from .admin_paths import AdminPaths
from .admin_scenes import AdminScenes
from .admin_settings import AdminSettings

_TABS = ["Szenen", "Pfade", "Einstellungen"]


class AdminMain(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self.setObjectName("AdminRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sidebar
        sidebar = QWidget()
        sidebar.setObjectName("AdminSidebar")
        sidebar.setFixedWidth(230)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(14, 18, 14, 18)
        sb_layout.setSpacing(8)

        title = QLabel("Fotobox")
        set_kind(title, "appname")
        subtitle = QLabel("Adminbereich")
        set_kind(subtitle, "subtitle")
        sb_layout.addWidget(title)
        sb_layout.addWidget(subtitle)
        sb_layout.addSpacing(18)

        self._tab_btns = {}
        for name in _TABS:
            btn = QPushButton(name)
            btn.setCheckable(True)
            set_kind(btn, "tab")
            btn.clicked.connect(lambda _, n=name: self._switch_tab(n))
            sb_layout.addWidget(btn)
            self._tab_btns[name] = btn
        sb_layout.addStretch()

        sb_layout.addWidget(make_separator())
        sb_layout.addSpacing(8)
        close_btn = QPushButton("✕  Schließen")
        set_kind(close_btn, "close")
        close_btn.clicked.connect(self._close)
        sb_layout.addWidget(close_btn)

        layout.addWidget(sidebar)

        # Content
        self.content = QStackedWidget()
        self.sub_views = {
            "Szenen": AdminScenes(app),
            "Pfade": AdminPaths(app),
            "Einstellungen": AdminSettings(app),
        }
        for sv in self.sub_views.values():
            self.content.addWidget(sv)
        layout.addWidget(self.content, 1)

        self._active_tab = _TABS[0]

        # Swappable design file – styles this widget and all children.
        self.setStyleSheet(theme.admin_stylesheet(app.config))

    # ------------------------------------------------------------------

    def on_enter(self):
        self.app.gpio.set_ready_led(False)
        self._switch_tab(self._active_tab)

    def _switch_tab(self, name: str):
        if name not in self.sub_views:
            return
        self._active_tab = name
        for n, b in self._tab_btns.items():
            b.setChecked(n == name)
        view = self.sub_views[name]
        self.content.setCurrentWidget(view)
        view.refresh()

    def _close(self):
        self.app.context.exit_admin()
        self.transition_to("start")
