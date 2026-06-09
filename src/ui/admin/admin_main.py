"""
Admin container screen (PyQt6).
Vertical sidebar (Schließen + tab buttons) and a QStackedWidget for content.
Tabs: Pfade | Szenen | Einstellungen.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QHBoxLayout, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import theme
from ..base_screen import BaseScreen
from .admin_paths import AdminPaths
from .admin_scenes import AdminScenes
from .admin_settings import AdminSettings

_TABS = ["Pfade", "Szenen", "Einstellungen"]


class AdminMain(BaseScreen):
    def __init__(self, app):
        super().__init__(app)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sidebar
        sidebar = QWidget()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(theme.SIDEBAR_STYLE)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(12, 16, 12, 16)
        sb_layout.setSpacing(8)

        close_btn = QPushButton("✕ Schließen")
        close_btn.setStyleSheet(theme.CLOSE_BTN_STYLE)
        close_btn.clicked.connect(self._close)
        sb_layout.addWidget(close_btn)
        sb_layout.addSpacing(20)

        self._tab_btns = {}
        for name in _TABS:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setStyleSheet(theme.TAB_BTN_STYLE)
            btn.clicked.connect(lambda _, n=name: self._switch_tab(n))
            sb_layout.addWidget(btn)
            self._tab_btns[name] = btn
        sb_layout.addStretch()

        layout.addWidget(sidebar)

        # Content
        self.content = QStackedWidget()
        self.sub_views = {
            "Pfade": AdminPaths(app),
            "Szenen": AdminScenes(app),
            "Einstellungen": AdminSettings(app),
        }
        for sv in self.sub_views.values():
            self.content.addWidget(sv)
        layout.addWidget(self.content, 1)

        self._active_tab = _TABS[0]

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
