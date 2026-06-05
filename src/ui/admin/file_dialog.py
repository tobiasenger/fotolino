"""
Shared helper for opening pygame_gui UIFileDialog.
Handles API differences between pygame_gui versions (allowed_extensions was
added in a later 0.6.x release and is absent in the version typically installed
on Raspberry Pi OS via pip).
"""
from __future__ import annotations
from pathlib import Path

import pygame
import pygame_gui


def open_file_dialog(
    manager: pygame_gui.UIManager,
    initial_path: Path | str,
    title: str = "Datei auswählen",
    extensions: set | None = None,
) -> pygame_gui.windows.UIFileDialog:
    """
    Open a UIFileDialog centred on the display.
    Falls back gracefully when 'allowed_extensions' is not supported.
    """
    surf  = pygame.display.get_surface()
    sw, sh = surf.get_size()
    rect  = pygame.Rect(sw // 2 - 340, sh // 2 - 280, 680, 560)
    start = str(Path(initial_path)) if Path(initial_path).exists() else str(Path.home())

    base_kwargs = dict(
        rect=rect,
        manager=manager,
        window_title=title,
        initial_file_path=start,
        allow_picking_directories=False,
        allow_existing_files_only=True,
    )

    # Try with allowed_extensions first (newer pygame_gui), fall back without it
    try:
        return pygame_gui.windows.UIFileDialog(
            **base_kwargs,
            allowed_extensions=extensions or set(),
        )
    except TypeError:
        return pygame_gui.windows.UIFileDialog(**base_kwargs)
