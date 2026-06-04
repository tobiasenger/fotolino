import pygame

# Custom event types.
# MUST use custom_type() so the IDs are reserved in pygame's internal counter
# before pygame_gui is imported and claims its own IDs via the same counter.
# Using USEREVENT + N directly would collide with pygame_gui's event types.
BUTTON_EVENT      = pygame.event.custom_type()  # GPIO or keyboard button press
SCREEN_TRANSITION = pygame.event.custom_type()  # Request a screen change

# Screen resolution
SCREEN_W = 1920
SCREEN_H = 1080

# Collage canvas
COLLAGE_W = 1800
COLLAGE_H = 1200

# Collage photo bounding boxes per capture count
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

# UI Colors
COLOR_BG         = (10, 10, 20)
COLOR_BG_DARK    = (5, 5, 10)
COLOR_TEXT       = (255, 255, 255)
COLOR_TEXT_DIM   = (180, 180, 180)
COLOR_ACCENT     = (255, 102, 0)
COLOR_SUCCESS    = (80, 200, 80)
COLOR_ERROR      = (220, 60, 60)
COLOR_WHITE      = (255, 255, 255)
COLOR_BLACK      = (0, 0, 0)
COLOR_OVERLAY    = (0, 0, 0, 160)     # semi-transparent black
COLOR_FLASH      = (255, 255, 255)

# Admin UI colors
ADMIN_BG         = (20, 20, 35)
ADMIN_PANEL      = (30, 30, 50)
ADMIN_HIGHLIGHT  = (50, 50, 80)
ADMIN_TAB_ACTIVE = (255, 102, 0)
ADMIN_TAB_IDLE   = (40, 40, 65)

# Scene duration limits (seconds)
SCENE_GREETING_MIN = 5
SCENE_GREETING_MAX = 25
SCENE_COLLAGE_DURATION = 10
SCENE_PRINT_DURATION   = 40

# Font sizes
FONT_HUGE    = 180
FONT_LARGE   = 90
FONT_MEDIUM  = 54
FONT_SMALL   = 36
FONT_TINY    = 24
