"""
Invoy App — design tokens.

Palette inspired by Apple's dark mode: near-black backgrounds, very
subtle borders, muted accent colours used only where they carry meaning.
"""

# ── Colours ────────────────────────────────────────────────────────────────

COLORS: dict[str, str] = {
    # Backgrounds
    "bg":       "#09090B",   # root window — near-black
    "surface":  "#131316",   # card / panel backgrounds
    "elevated": "#1C1C1F",   # hover rows, selected states, raised chips

    # Borders & separators
    "border":   "#27272A",   # hairlines — almost invisible against surface

    # Text hierarchy
    "text":     "#FAFAFA",   # primary — titles, activity text
    "subtext":  "#A1A1AA",   # secondary — labels, category headers
    "muted":    "#52525B",   # tertiary — timestamps, inactive elements

    # Interactive
    "accent":          "#3B82F6",   # blue — buttons, links; used sparingly
    "accent_hover":    "#2563EB",

    # Status
    "recording":  "#F87171",   # muted red — pulse dot during recording
    "loading":    "#FBBF24",   # amber — model loading
    "success":    "#4ADE80",   # muted green — session complete
    "danger":     "#F87171",   # same muted red for errors

    # Application context chips (muted, 60% saturation)
    "ctx_code":    "#A78BFA",   # VS Code / editors      — muted violet
    "ctx_browser": "#60A5FA",   # Chrome / Firefox        — muted blue
    "ctx_term":    "#34D399",   # Terminal / shell        — muted emerald
    "ctx_other":   "#9CA3AF",   # fallback                — neutral grey
}

# ── Typography ─────────────────────────────────────────────────────────────
# Segoe UI is always present on Windows 10/11 and gives a clean sans result.
# These are (family, size, weight?) tuples for customtkinter font= parameter.

FONTS: dict[str, tuple] = {
    "wordmark":  ("Segoe UI", 16, "bold"),       # "Invoy" in header
    "display":   ("Segoe UI", 32, "bold"),        # idle state large title
    "heading":   ("Segoe UI", 17, "bold"),        # section headings
    "body":      ("Segoe UI", 15),                # activity card text (hero)
    "body_bold": ("Segoe UI", 15, "bold"),
    "ui":        ("Segoe UI", 13),                # UI labels, bullets
    "ui_bold":   ("Segoe UI", 13, "bold"),        # category titles
    "status":    ("Segoe UI", 12),                # header status string
    "small":     ("Segoe UI", 11),                # secondary labels
    "timestamp": ("Segoe UI", 11),                # timestamps, muted
    "mono":      ("Consolas", 13),                # timer, technical values
}

# ── Spacing (8-px grid) ────────────────────────────────────────────────────

SPACING: dict[str, int] = {
    "xs":  4,
    "sm":  8,
    "md":  16,
    "lg":  24,
    "xl":  40,
    "xxl": 64,
}

# ── Geometry ───────────────────────────────────────────────────────────────

RADIUS    = 10    # default card / button corner radius
RADIUS_SM = 6     # small elements: chips, tags
RADIUS_XS = 4     # tiny elements

HEADER_H  = 52    # header bar height in pixels
CARD_PAD_X = 20   # horizontal padding inside activity cards
CARD_PAD_Y = 16   # vertical padding inside activity cards
CARD_GAP   = 6    # gap between consecutive cards

# ── Window ─────────────────────────────────────────────────────────────────

WINDOW_W     = 1100
WINDOW_H     = 720
WINDOW_MIN_W = 900
WINDOW_MIN_H = 600
