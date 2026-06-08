"""
Admin Paths tab (PyQt6).
Left: list of paths with probability/photo info + add/delete buttons.
Right: editor form (name, probability, greeting/collage/print scene dropdowns, capture count).
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QListWidget, QListWidgetItem, QScrollArea,
)
from PyQt6.QtCore import Qt

_BTN = (
    "QPushButton { background: #2a2a50; color: white; border: 1px solid #444488; "
    "border-radius: 5px; padding: 8px 14px; } QPushButton:hover { border-color: #ff6600; }"
)
_DEL = (
    "QPushButton { background: #5a2030; color: white; border: 1px solid #884444; "
    "border-radius: 5px; padding: 8px 14px; } QPushButton:hover { border-color: #ff6600; }"
)
_CAPTURE_OPTS = [
    ("0 – Nur Begrüßung", 0), ("1 Foto", 1), ("2 Fotos", 2),
    ("3 Fotos", 3), ("4 Fotos", 4),
]


class AdminPaths(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._editing_id: str | None = None

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)

        # ---- Left: list ----
        left = QVBoxLayout()
        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_select)
        left.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Neuer Pfad")
        add_btn.setStyleSheet(_BTN)
        add_btn.clicked.connect(self._new_path)
        self._del_btn = QPushButton("Löschen")
        self._del_btn.setStyleSheet(_DEL)
        self._del_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(self._del_btn)
        left.addLayout(btn_row)

        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(440)
        root.addWidget(left_w)

        # ---- Right: editor ----
        self._editor = QScrollArea()
        self._editor.setWidgetResizable(True)
        self._editor_inner = QWidget()
        self._form = QFormLayout(self._editor_inner)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self._editor.setWidget(self._editor_inner)
        root.addWidget(self._editor, 1)

        self._build_form()
        self._set_editor_enabled(False)

    # ------------------------------------------------------------------

    def _build_form(self):
        self._name = QLineEdit()
        self._prob = QLineEdit()
        self._prob_info = QLabel("")
        self._greeting = QComboBox()
        self._capture = QComboBox()
        for label, _ in _CAPTURE_OPTS:
            self._capture.addItem(label)
        self._collage = QComboBox()
        self._print = QComboBox()

        self._form.addRow("Name:", self._name)
        self._form.addRow("Wahrscheinlichkeit (%):", self._prob)
        self._form.addRow("", self._prob_info)
        self._form.addRow("Begrüßungsszene:", self._greeting)
        self._form.addRow("Aufnahmen:", self._capture)
        self._form.addRow("Collage-Szene (bei ≥1 Foto):", self._collage)
        self._form.addRow("Druck-Szene (bei ≥1 Foto):", self._print)

        save = QPushButton("Speichern")
        save.setStyleSheet(_BTN)
        save.clicked.connect(self._save)
        self._save_btn = save
        self._form.addRow("", save)

    def _populate_scene_dropdowns(self):
        def fill(combo: QComboBox, scene_type: str):
            combo.clear()
            combo.addItem("(keine)", "")
            for s in self.app.config.get_scenes_by_type(scene_type):
                combo.addItem(f"{s.get('name', s['id'])} [{s['id']}]", s["id"])

        fill(self._greeting, "greeting")
        fill(self._collage, "collage")
        fill(self._print, "print")

    @staticmethod
    def _select_id(combo: QComboBox, scene_id: str):
        idx = combo.findData(scene_id)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    # ------------------------------------------------------------------

    def refresh(self):
        self._reload_list()
        self._editing_id = None
        self._set_editor_enabled(False)

    def _reload_list(self):
        self._list.clear()
        for path in self.app.config.get_paths():
            pid = path["id"]
            name = path.get("name", "(kein Name)")
            prob = (self.app.config.compute_default_probability()
                    if path.get("is_default") else path.get("probability", 0))
            tag = " ★" if path.get("is_default") else ""
            capture = path.get("scenes", {}).get("capture_count", 0)
            item = QListWidgetItem(f"{name}{tag}  |  {prob}%  |  {capture} Fotos")
            item.setData(Qt.ItemDataRole.UserRole, pid)
            self._list.addItem(item)

    # ------------------------------------------------------------------

    def _on_select(self, item: QListWidgetItem):
        pid = item.data(Qt.ItemDataRole.UserRole)
        path = self._find(pid)
        if path:
            self._load_into_editor(path)

    def _new_path(self):
        self._editing_id = "__new__"
        self._populate_scene_dropdowns()
        self._name.setText("")
        self._prob.setText("5")
        self._prob.setEnabled(True)
        self._prob_info.setText("")
        self._greeting.setCurrentIndex(0)
        self._capture.setCurrentIndex(0)
        self._collage.setCurrentIndex(0)
        self._print.setCurrentIndex(0)
        self._set_editor_enabled(True)

    def _load_into_editor(self, path: dict):
        self._editing_id = path["id"]
        self._populate_scene_dropdowns()
        self._name.setText(path.get("name", ""))
        scenes = path.get("scenes", {})
        if path.get("is_default"):
            self._prob.setText(str(self.app.config.compute_default_probability()))
            self._prob.setEnabled(False)
            self._prob_info.setText("Standard-Pfad – Wahrscheinlichkeit automatisch berechnet.")
        else:
            self._prob.setText(str(path.get("probability", 5)))
            self._prob.setEnabled(True)
            self._prob_info.setText("")
        self._select_id(self._greeting, scenes.get("greeting", ""))
        self._capture.setCurrentIndex(min(scenes.get("capture_count", 0), 4))
        self._select_id(self._collage, scenes.get("collage", ""))
        self._select_id(self._print, scenes.get("print", ""))
        self._set_editor_enabled(True)

    def _set_editor_enabled(self, on: bool):
        self._editor_inner.setEnabled(on)

    # ------------------------------------------------------------------

    def _save(self):
        name = self._name.text().strip()
        if not name:
            self.app.show_notification("Bitte einen Namen eingeben.", level="warning")
            return
        try:
            prob = int(self._prob.text())
        except ValueError:
            prob = 0
        count = _CAPTURE_OPTS[self._capture.currentIndex()][1]

        scenes_dict = {
            "greeting": self._greeting.currentData() or "",
            "capture_count": count,
        }
        if count > 0:
            scenes_dict["collage"] = self._collage.currentData() or ""
            scenes_dict["print"] = self._print.currentData() or ""

        if self._editing_id == "__new__":
            self.app.config.add_path({
                "name": name, "probability": prob,
                "is_default": not self.app.config.get_paths(),
                "scenes": scenes_dict,
            })
        else:
            existing = self._find(self._editing_id)
            if existing:
                updated = dict(existing)
                updated["name"] = name
                if not existing.get("is_default"):
                    updated["probability"] = prob
                updated["scenes"] = scenes_dict
                self.app.config.update_path(self._editing_id, updated)

        self.app.show_notification("Pfad gespeichert.", duration=3.0, level="info")
        self.refresh()

    def _delete_selected(self):
        item = self._list.currentItem()
        if not item:
            return
        pid = item.data(Qt.ItemDataRole.UserRole)
        self.app.config.delete_path(pid)
        self.refresh()

    def _find(self, pid: str) -> dict | None:
        for p in self.app.config.get_paths():
            if p["id"] == pid:
                return p
        return None
