"""
Admin Paths tab (PyQt6).
Left: list of paths with probability info + add/delete buttons.
Right: editor form. Common fields (name, path type, probability) plus either
the standard scene flow (greeting/captures/collage/print dropdowns) or – for
custom paths – an inline list of 1–MAX_PATH_SEGMENTS segment editors.

Segment types: image, GIF (loop or play-once), live camera, capture
(standard capture flow, builds the collage in the background) and print
(collage view followed by the print view, like the standard collage/print
screens, with per-phase background/overlay/audio). Segments run in list
order; audio always plays once per segment (print: once per phase).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QListWidget, QListWidgetItem, QScrollArea,
)

from ...audio import AudioPlayer
from ...constants import (
    MAX_PATH_SEGMENTS, SEGMENT_DURATION_DEFAULT, SEGMENT_DURATION_RANGE,
)
from ..widgets import (
    FileSelectRow, add_form_section, make_hint, make_separator, set_kind,
)

_CAPTURE_OPTS = [("1 Foto", 1), ("2 Fotos", 2), ("3 Fotos", 3), ("4 Fotos", 4)]

_PATH_TYPES = [("Standard-Pfad", "standard"), ("Individueller Pfad", "custom")]

_SEGMENT_TYPES = [
    ("Bild", "image"), ("GIF", "gif"), ("Kamera", "camera"),
    ("Aufnahme", "capture"), ("Druck", "print"),
]

_IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
_GIF_EXTS = {".gif"}
_OVERLAY_EXTS = {".png", ".gif"}
_AUDIO_EXTS = {".mp3", ".wav", ".ogg"}

_SEGMENT_HINTS = {
    "image": "",
    "gif": "",
    "camera": "Live-Kamerabild (Spiegel) ohne Foto-Aufnahme.",
    "capture": "Standard-Aufnahmeablauf mit Countdown; die Collage wird "
               "anschließend im Hintergrund erstellt und gespeichert.",
    "print": "Zeigt zuerst die Collage-Erstellung (Diashow der Fotos, Dauer = "
             "Collage-Dauer) und druckt danach die zuletzt erstellte Collage "
             "(Dauer = Druckdauer, beides Einstellungen → Zeiten). Audio darf "
             "jeweils höchstens so lang sein wie die zugehörige Dauer.",
}


class _SegmentEditor(QWidget):
    """Inline editor for one segment of a custom path."""

    remove_requested = pyqtSignal(object)

    def __init__(self, config):
        super().__init__()
        self._config = config

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(make_separator())

        header = QHBoxLayout()
        self._title = QLabel("Segment")
        set_kind(self._title, "section")
        header.addWidget(self._title)
        header.addStretch()
        remove_btn = QPushButton("Entfernen")
        set_kind(remove_btn, "danger")
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        header.addWidget(remove_btn)
        layout.addLayout(header)

        form = QFormLayout()
        form.setVerticalSpacing(8)
        layout.addLayout(form)

        self._type = QComboBox()
        for label, key in _SEGMENT_TYPES:
            self._type.addItem(label, key)
        self._type.currentIndexChanged.connect(self._update_visibility)

        self._image = FileSelectRow(config, _IMAGE_EXTS, "Bild")
        self._gif = FileSelectRow(config, _GIF_EXTS, "GIF")
        self._overlay = FileSelectRow(config, _OVERLAY_EXTS, "Overlay")
        self._audio = FileSelectRow(config, _AUDIO_EXTS, "Audio")
        # Print segment: separate media per phase (collage view, then print view)
        self._collage_image = FileSelectRow(config, _IMAGE_EXTS, "Hintergrund")
        self._collage_overlay = FileSelectRow(config, _OVERLAY_EXTS, "Overlay")
        self._collage_audio = FileSelectRow(config, _AUDIO_EXTS, "Audio")
        self._print_image = FileSelectRow(config, _IMAGE_EXTS, "Hintergrund")
        self._print_overlay = FileSelectRow(config, _OVERLAY_EXTS, "Overlay")
        self._print_audio = FileSelectRow(config, _AUDIO_EXTS, "Audio")
        self._duration = QLineEdit(f"{SEGMENT_DURATION_DEFAULT:g}")
        self._loop = QComboBox()
        self._loop.addItem("Schleife (bis Segmentende)", True)
        self._loop.addItem("Einmal abspielen (danach Schwarzbild)", False)
        self._capture = QComboBox()
        for label, _ in _CAPTURE_OPTS:
            self._capture.addItem(label)

        self._lbl_type = QLabel("Typ:")
        self._lbl_image = QLabel("Bilddatei (.jpg/.png):")
        self._lbl_gif = QLabel("GIF-Datei (.gif):")
        self._lbl_overlay = QLabel("Overlay (.png/.gif, optional):")
        self._lbl_audio = QLabel("Audio (.mp3/.wav/.ogg, optional):")
        self._lbl_collage_image = QLabel("Collage-Hintergrund (.jpg/.png, optional):")
        self._lbl_collage_overlay = QLabel("Collage-Overlay (.png/.gif, optional):")
        self._lbl_collage_audio = QLabel("Collage-Audio (.mp3/.wav/.ogg, optional):")
        self._lbl_print_image = QLabel("Druck-Hintergrund (.jpg/.png, optional):")
        self._lbl_print_overlay = QLabel("Druck-Overlay (.png/.gif, optional):")
        self._lbl_print_audio = QLabel("Druck-Audio (.mp3/.wav/.ogg, optional):")
        self._lbl_duration = QLabel("Dauer (Sekunden):")
        self._lbl_loop = QLabel("GIF-Wiedergabe:")
        self._lbl_capture = QLabel("Aufnahmen:")

        form.addRow(self._lbl_type, self._type)
        form.addRow(self._lbl_image, self._image)
        form.addRow(self._lbl_gif, self._gif)
        form.addRow(self._lbl_overlay, self._overlay)
        form.addRow(self._lbl_audio, self._audio)
        form.addRow(self._lbl_collage_image, self._collage_image)
        form.addRow(self._lbl_collage_overlay, self._collage_overlay)
        form.addRow(self._lbl_collage_audio, self._collage_audio)
        form.addRow(self._lbl_print_image, self._print_image)
        form.addRow(self._lbl_print_overlay, self._print_overlay)
        form.addRow(self._lbl_print_audio, self._print_audio)
        form.addRow(self._lbl_duration, self._duration)
        form.addRow(self._lbl_loop, self._loop)
        form.addRow(self._lbl_capture, self._capture)

        self._hint = QLabel()
        self._hint.setWordWrap(True)
        set_kind(self._hint, "hint")
        form.addRow(self._hint)

        self._update_visibility()

    # ------------------------------------------------------------------

    def set_index(self, index: int):
        self._title.setText(f"Segment {index}")

    def segment_type(self) -> str:
        return self._type.currentData()

    def _update_visibility(self):
        stype = self.segment_type()
        is_print = stype == "print"
        for label, row, visible in (
            (self._lbl_image, self._image, stype == "image"),
            (self._lbl_gif, self._gif, stype == "gif"),
            (self._lbl_overlay, self._overlay, stype in ("image", "camera")),
            (self._lbl_audio, self._audio,
             stype in ("image", "gif", "camera")),
            (self._lbl_collage_image, self._collage_image, is_print),
            (self._lbl_collage_overlay, self._collage_overlay, is_print),
            (self._lbl_collage_audio, self._collage_audio, is_print),
            (self._lbl_print_image, self._print_image, is_print),
            (self._lbl_print_overlay, self._print_overlay, is_print),
            (self._lbl_print_audio, self._print_audio, is_print),
            (self._lbl_duration, self._duration,
             stype in ("image", "gif", "camera")),
            (self._lbl_loop, self._loop, stype == "gif"),
            (self._lbl_capture, self._capture, stype == "capture"),
        ):
            label.setVisible(visible)
            row.setVisible(visible)
        hint = _SEGMENT_HINTS.get(stype, "")
        self._hint.setText(hint)
        self._hint.setVisible(bool(hint))

    # ------------------------------------------------------------------

    def load(self, seg: dict):
        idx = self._type.findData(seg.get("type", "image"))
        self._type.setCurrentIndex(idx if idx >= 0 else 0)
        is_print = seg.get("type") == "print"
        self._image.setText("" if is_print else seg.get("image", ""))
        self._gif.setText(seg.get("gif", ""))
        self._overlay.setText("" if is_print else seg.get("overlay", ""))
        self._audio.setText("" if is_print else seg.get("audio", ""))
        self._collage_image.setText(seg.get("collage_image", ""))
        self._collage_overlay.setText(seg.get("collage_overlay", ""))
        self._collage_audio.setText(seg.get("collage_audio", ""))
        # Older print segments stored their media in the flat keys.
        self._print_image.setText(
            seg.get("print_image") or (seg.get("image", "") if is_print else ""))
        self._print_overlay.setText(
            seg.get("print_overlay") or (seg.get("overlay", "") if is_print else ""))
        self._print_audio.setText(
            seg.get("print_audio") or (seg.get("audio", "") if is_print else ""))
        try:
            dur = float(seg.get("duration", SEGMENT_DURATION_DEFAULT))
        except (TypeError, ValueError):
            dur = SEGMENT_DURATION_DEFAULT
        self._duration.setText(f"{dur:g}")
        self._loop.setCurrentIndex(0 if seg.get("loop", True) else 1)
        try:
            count = int(seg.get("capture_count", 1))
        except (TypeError, ValueError):
            count = 1
        self._capture.setCurrentIndex(min(max(count, 1), 4) - 1)
        self._update_visibility()

    def values(self) -> tuple[dict | None, str | None]:
        """Collect the segment dict, or (None, error message)."""
        stype = self.segment_type()
        seg: dict = {"type": stype}

        if stype in ("image", "gif", "camera"):
            duration, err = self._parse_duration()
            if err:
                return None, err
            seg["duration"] = duration

        if stype not in ("capture", "print"):
            seg["audio"] = self._audio.text()

        if stype == "image":
            if not self._image.text():
                return None, "Bitte eine Bilddatei auswählen."
            seg["image"] = self._image.text()
            seg["overlay"] = self._overlay.text()
        elif stype == "gif":
            if not self._gif.text():
                return None, "Bitte eine GIF-Datei auswählen."
            seg["gif"] = self._gif.text()
            seg["loop"] = bool(self._loop.currentData())
        elif stype == "camera":
            seg["overlay"] = self._overlay.text()
        elif stype == "capture":
            seg["capture_count"] = _CAPTURE_OPTS[self._capture.currentIndex()][1]
        elif stype == "print":
            for phase, label, audio_row in (
                ("collage", "Collage-Audio", self._collage_audio),
                ("print", "Druck-Audio", self._print_audio),
            ):
                err = self._check_phase_audio(phase, label, audio_row.text())
                if err:
                    return None, err
            seg["collage_image"] = self._collage_image.text()
            seg["collage_overlay"] = self._collage_overlay.text()
            seg["collage_audio"] = self._collage_audio.text()
            seg["print_image"] = self._print_image.text()
            seg["print_overlay"] = self._print_overlay.text()
            seg["print_audio"] = self._print_audio.text()
        return seg, None

    def _check_phase_audio(self, scene_type: str, label: str,
                           audio: str) -> str | None:
        """Same limit as standard collage/print scenes: the audio may be at
        most as long as the configured scene duration."""
        if not audio:
            return None
        duration = AudioPlayer.get_audio_duration(
            self._config.resolve_asset(audio)) or 0.0
        hi = self._config.scene_duration_limits(scene_type)[1]
        if duration > hi:
            return (f"{label} ({duration:.1f}s) ist länger als die "
                    f"konfigurierte Szenendauer ({hi:g}s). Kürzere Datei "
                    f"wählen oder Dauer unter Einstellungen → Zeiten erhöhen.")
        return None

    def _parse_duration(self) -> tuple[float, str | None]:
        text = self._duration.text().strip().replace(",", ".")
        try:
            duration = float(text)
        except ValueError:
            return 0.0, "Ungültige Dauer – bitte eine Zahl eingeben."
        lo, hi = SEGMENT_DURATION_RANGE
        if not lo <= duration <= hi:
            return 0.0, (f"Dauer muss zwischen {lo:g} und {hi:g} Sekunden "
                         f"liegen.")
        return round(duration, 1), None


class AdminPaths(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._editing_id: str | None = None
        self._segment_editors: list[_SegmentEditor] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        # ---- Header ----
        title = QLabel("Pfade")
        set_kind(title, "title")
        root.addWidget(title)
        root.addWidget(make_hint(
            "Ein Pfad wird beim Start per Wahrscheinlichkeit ausgewählt. "
            "Standard-Pfade verknüpfen Szenen zum festen Ablauf Begrüßung → "
            "Fotos → Collage → Druck (Szenen zuerst im Tab „Szenen“ "
            f"erstellen). Individuelle Pfade bestehen aus einer freien Abfolge "
            f"von bis zu {MAX_PATH_SEGMENTS} Segmenten (Bild, GIF, Kamera, "
            "Aufnahme, Druck)."))

        content = QHBoxLayout()
        content.setSpacing(16)
        root.addLayout(content, 1)

        # ---- Left: list ----
        left = QVBoxLayout()
        left.setSpacing(10)
        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_select)
        left.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Neuer Pfad")
        set_kind(add_btn, "primary")
        add_btn.clicked.connect(self._new_path)
        self._del_btn = QPushButton("Löschen")
        set_kind(self._del_btn, "danger")
        self._del_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(add_btn, 1)
        btn_row.addWidget(self._del_btn)
        left.addLayout(btn_row)

        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(440)
        content.addWidget(left_w)

        # ---- Right: editor ----
        self._editor = QScrollArea()
        self._editor.setWidgetResizable(True)
        self._editor_inner = QWidget()
        self._form = QFormLayout(self._editor_inner)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self._form.setVerticalSpacing(10)
        self._editor.setWidget(self._editor_inner)
        content.addWidget(self._editor, 1)

        self._build_form()
        self._set_editor_enabled(False)

    # ------------------------------------------------------------------

    def _build_form(self):
        self._editor_status = QLabel()
        set_kind(self._editor_status, "section")
        self._form.addRow(self._editor_status)

        self._name = QLineEdit()
        self._ptype = QComboBox()
        for label, key in _PATH_TYPES:
            self._ptype.addItem(label, key)
        self._ptype.currentIndexChanged.connect(self._update_type_visibility)
        self._prob = QLineEdit()
        self._prob_info = QLabel("")
        set_kind(self._prob_info, "hint")

        self._form.addRow("Name:", self._name)
        self._form.addRow("Pfadtyp:", self._ptype)
        self._form.addRow("Wahrscheinlichkeit (%):", self._prob)
        self._form.addRow("", self._prob_info)

        self._form.addRow(self._build_standard_section())
        self._form.addRow(self._build_custom_section())

        save = QPushButton("Pfad speichern")
        set_kind(save, "primary")
        save.clicked.connect(self._save)
        self._save_btn = save
        self._form.addRow("", save)

    def _build_standard_section(self) -> QWidget:
        self._std_w = QWidget()
        form = QFormLayout(self._std_w)
        form.setContentsMargins(0, 0, 0, 0)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setVerticalSpacing(10)

        self._greeting = QComboBox()
        self._capture = QComboBox()
        for label, _ in _CAPTURE_OPTS:
            self._capture.addItem(label)
        self._collage = QComboBox()
        self._print = QComboBox()

        add_form_section(form, "Ablauf")
        form.addRow("Begrüßungsszene:", self._greeting)
        form.addRow("Aufnahmen:", self._capture)
        form.addRow("Collage-Szene:", self._collage)
        form.addRow("Druck-Szene:", self._print)
        return self._std_w

    def _build_custom_section(self) -> QWidget:
        self._custom_w = QWidget()
        box = QVBoxLayout(self._custom_w)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)

        box.addWidget(make_separator())
        section = QLabel("Segmente")
        set_kind(section, "section")
        box.addWidget(section)
        box.addWidget(make_hint(
            f"Die Segmente laufen in dieser Reihenfolge ab (mindestens 1, "
            f"höchstens {MAX_PATH_SEGMENTS}). Ein Druck-Segment druckt die "
            "zuletzt erstellte Collage – dafür vorher ein Aufnahme-Segment "
            "einplanen."))

        seg_holder = QWidget()
        self._seg_layout = QVBoxLayout(seg_holder)
        self._seg_layout.setContentsMargins(0, 0, 0, 0)
        self._seg_layout.setSpacing(10)
        box.addWidget(seg_holder)

        self._add_seg_btn = QPushButton("+ Segment hinzufügen")
        set_kind(self._add_seg_btn, "primary")
        self._add_seg_btn.clicked.connect(lambda: self._add_segment_editor())
        box.addWidget(self._add_seg_btn)
        return self._custom_w

    def _update_type_visibility(self):
        is_custom = self._ptype.currentData() == "custom"
        self._std_w.setVisible(not is_custom)
        self._custom_w.setVisible(is_custom)

    # ------------------------------------------------------------------
    # Segment editor management
    # ------------------------------------------------------------------

    def _add_segment_editor(self, seg: dict | None = None):
        if len(self._segment_editors) >= MAX_PATH_SEGMENTS:
            return
        editor = _SegmentEditor(self.app.config)
        editor.remove_requested.connect(self._remove_segment_editor)
        if seg:
            editor.load(seg)
        self._segment_editors.append(editor)
        self._seg_layout.addWidget(editor)
        self._renumber_segments()

    def _remove_segment_editor(self, editor: _SegmentEditor):
        if editor in self._segment_editors:
            self._segment_editors.remove(editor)
            self._seg_layout.removeWidget(editor)
            editor.deleteLater()
            self._renumber_segments()

    def _clear_segment_editors(self):
        for editor in self._segment_editors:
            self._seg_layout.removeWidget(editor)
            editor.deleteLater()
        self._segment_editors = []
        self._renumber_segments()

    def _renumber_segments(self):
        for i, editor in enumerate(self._segment_editors, start=1):
            editor.set_index(i)
        self._add_seg_btn.setEnabled(
            len(self._segment_editors) < MAX_PATH_SEGMENTS)

    # ------------------------------------------------------------------

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
            if path.get("type") == "custom":
                n = len(path.get("segments", []))
                detail = f"{n} Segment{'e' if n != 1 else ''}"
            else:
                capture = path.get("scenes", {}).get("capture_count", 0)
                detail = f"{capture} Fotos"
            item = QListWidgetItem(f"{name}{tag}  |  {prob}%  |  {detail}")
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
        self._editor_status.setText("Neuer Pfad")
        self._populate_scene_dropdowns()
        self._name.setText("")
        self._ptype.setCurrentIndex(0)
        self._prob.setText("5")
        self._prob.setEnabled(True)
        self._prob_info.setText("")
        self._greeting.setCurrentIndex(0)
        self._capture.setCurrentIndex(0)
        self._collage.setCurrentIndex(0)
        self._print.setCurrentIndex(0)
        self._clear_segment_editors()
        self._update_type_visibility()
        self._set_editor_enabled(True)

    def _load_into_editor(self, path: dict):
        self._editing_id = path["id"]
        self._editor_status.setText(
            f"Pfad bearbeiten: {path.get('name', '(kein Name)')}")
        self._populate_scene_dropdowns()
        self._name.setText(path.get("name", ""))
        idx = self._ptype.findData(path.get("type", "standard"))
        self._ptype.setCurrentIndex(idx if idx >= 0 else 0)
        if path.get("is_default"):
            self._prob.setText(str(self.app.config.compute_default_probability()))
            self._prob.setEnabled(False)
            self._prob_info.setText(
                "★-Pfad – Wahrscheinlichkeit wird automatisch berechnet "
                "(Rest zu 100 %).")
        else:
            self._prob.setText(str(path.get("probability", 5)))
            self._prob.setEnabled(True)
            self._prob_info.setText("")

        scenes = path.get("scenes", {})
        self._select_id(self._greeting, scenes.get("greeting", ""))
        count = scenes.get("capture_count", 1)
        self._capture.setCurrentIndex(min(max(count, 1), 4) - 1)
        self._select_id(self._collage, scenes.get("collage", ""))
        self._select_id(self._print, scenes.get("print", ""))

        self._clear_segment_editors()
        for seg in path.get("segments", [])[:MAX_PATH_SEGMENTS]:
            self._add_segment_editor(seg)

        self._update_type_visibility()
        self._set_editor_enabled(True)

    def _set_editor_enabled(self, on: bool):
        self._editor_inner.setEnabled(on)
        if not on:
            self._editor_status.setText(
                "Pfad links auswählen oder „+ Neuer Pfad“ erstellen")

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

        data = self._collect_path_data(name)
        if data is None:
            return

        if self._editing_id == "__new__":
            data["probability"] = prob
            data["is_default"] = not self.app.config.get_paths()
            self.app.config.add_path(data)
        else:
            existing = self._find(self._editing_id)
            if existing:
                data["is_default"] = existing.get("is_default", False)
                data["probability"] = (existing.get("probability", 0)
                                       if existing.get("is_default") else prob)
                self.app.config.update_path(self._editing_id, data)

        self.app.show_notification("Pfad gespeichert.", duration=3.0, level="info")
        self.refresh()

    def _collect_path_data(self, name: str) -> dict | None:
        """Type-specific part of the path dict; None (+notification) on error."""
        if self._ptype.currentData() == "custom":
            if not self._segment_editors:
                self.app.show_notification(
                    "Bitte mindestens ein Segment hinzufügen.", level="warning")
                return None
            segments = []
            for i, editor in enumerate(self._segment_editors, start=1):
                seg, err = editor.values()
                if err:
                    self.app.show_notification(
                        f"Segment {i}: {err}", duration=6.0, level="warning")
                    return None
                segments.append(seg)
            return {"name": name, "type": "custom", "segments": segments}

        count = _CAPTURE_OPTS[self._capture.currentIndex()][1]
        return {
            "name": name, "type": "standard",
            "scenes": {
                "greeting": self._greeting.currentData() or "",
                "capture_count": count,
                "collage": self._collage.currentData() or "",
                "print": self._print.currentData() or "",
            },
        }

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
