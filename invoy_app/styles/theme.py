"""
Invoy App — design tokens.

Apple-inspired dark palette that maps well to customtkinter's colour API.
All components import from here — never hardcode hex values in widgets.
"""

COLORS: dict[str, str] = {
    "bg":      "#0F0F0F",   # root window background
    "surface": "#1C1C1E",   # card / panel background
    "raised":  "#2C2C2E",   # slightly elevated surface (alt rows, badges)
    "accent":  "#0A84FF",   # Apple blue — buttons, status dot, accent borders
    "accent_hover": "#0070E0",
    "danger":  "#FF453A",   # red — stop button, error states
    "success": "#30D158",   # green — recording indicator
    "text":    "#FFFFFF",
    "subtext": "#8E8E93",   # secondary labels, timestamps
    "border":  "#38383A",
    "separator": "#2C2C2E",
}

# Font families — Segoe UI is always present on Windows; falls back gracefully.
FONTS: dict[str, tuple] = {
    "heading": ("Segoe UI", 18, "bold"),
    "subheading": ("Segoe UI", 14, "bold"),
    "body":    ("Segoe UI", 13),
    "body_bold": ("Segoe UI", 13, "bold"),
    "mono":    ("Consolas", 12),
    "small":   ("Segoe UI", 11),
    "tiny":    ("Segoe UI", 9),
}

SPACING: dict[str, int] = {
    "xs": 4,
    "sm": 8,
    "md": 16,
    "lg": 24,
    "xl": 32,
}

RADIUS = 12          # default corner_radius for all CTk widgets
RADIUS_SM = 8        # smaller radius for inner cards
RADIUS_BTN = 24      # pill-shaped main action button

# Window dimensions
WINDOW_W = 960
WINDOW_H = 700
WINDOW_MIN_W = 820
WINDOW_MIN_H = 580

LEFT_PANEL_W = 290   # fixed left column width
