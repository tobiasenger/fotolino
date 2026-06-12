"""Application-wide constants (display geometry, collage layouts, timing, fonts)."""

# Screen resolution (fallback if not configured in settings.json)
SCREEN_W = 1920
SCREEN_H = 1080

# Collage canvas (must match the printable area / overlay PNGs)
COLLAGE_W = 1800
COLLAGE_H = 1200

# Collage photo bounding boxes per capture count.
# Each slot: (x, y, w, h, rotation_degrees)
COLLAGE_LAYOUTS = {
    1: [
        (100, 100, 1600, 1000, 0),
    ],
    2: [
        (80,  80, 790, 1040, 90),
        (930, 80, 790, 1040, 90),
    ],
    3: [
        (60,   60, 1100, 1080, 0),
        (1200, 60,  540,  520, 0),
        (1200, 620, 540,  520, 0),
    ],
    4: [
        (20,  60, 820, 520, 0),
        (880, 60, 820, 520, 0),
        (100, 620, 820, 520, 0),
        (960, 620, 820, 520, 0),
    ],
}

# Foreground media panel (slideshow on the collage screen, finished collage
# on the print screen): x, y, w, h in 1920x1080 design coordinates.
MEDIA_PANEL_RECT = (465, 160, 990, 660)

# Progress bar: full screen width, flush with the bottom edge (design height).
PROGRESS_BAR_H = 8

# Base background color used when a screen has no background image
COLOR_BG = (10, 10, 20)

# Scene durations are configured in the admin menu (settings.json key
# "scene_durations"). These are the allowed value ranges per setting and
# the factory defaults.
SCENE_DURATION_RANGES = {
    "greeting_min": (5, 10),    # minimum greeting duration
    "greeting_max": (30, 60),   # maximum greeting duration
    "collage": (10, 25),        # fixed collage screen duration
    "print": (30, 60),          # fixed print screen duration
}
SCENE_DURATION_DEFAULTS = {
    "greeting_min": 5,
    "greeting_max": 30,
    "collage": 15,
    "print": 40,
}

# Typography
FONT_FAMILY = "DejaVu Sans"
FONT_HUGE = 180
FONT_LARGE = 90
FONT_MEDIUM = 54
FONT_SMALL = 36
