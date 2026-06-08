"""
Native file-picker helper using QFileDialog.
"""
from pathlib import Path

from PyQt6.QtWidgets import QFileDialog


def open_file_dialog(parent, initial_path, title="Datei auswählen", extensions=None):
    """
    Open a native file-open dialog.

    extensions: optional iterable of suffixes (with dot), e.g. {".wav", ".mp3"}.
    Returns the selected file path as a string, or None if cancelled.
    """
    try:
        start = str(Path(initial_path)) if initial_path and Path(initial_path).exists() \
            else str(Path.home())
    except Exception:
        start = str(Path.home())

    if extensions:
        ext_str = " ".join(f"*{e}" for e in sorted(extensions))
        filter_str = f"Erlaubte Dateien ({ext_str});;Alle Dateien (*)"
    else:
        filter_str = "Alle Dateien (*)"

    path, _ = QFileDialog.getOpenFileName(parent, title, start, filter_str)
    return path if path else None
