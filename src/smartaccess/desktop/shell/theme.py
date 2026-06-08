"""SmartAccess dark workbench theme — black / white / blue, high contrast.

Visual direction adapts a Linear-style dark system: a near-black canvas with a
faint blue tint, a four-step surface ladder carrying hierarchy without shadow,
hairline borders, a single vivid-blue accent, and a high-contrast ink hierarchy.

Hard rule from product feedback: never gray text on a gray fill. Every text
role keeps a strong contrast ratio against the surface it sits on.
"""

from __future__ import annotations

# --- Surface ladder (canvas -> lifted) ---------------------------------- #
CANVAS = "#0a0c11"          # deepest background, faint blue tint (not pure black)
SURFACE_1 = "#13161d"       # cards, panels
SURFACE_2 = "#1a1e27"       # nested / hovered surfaces, inputs
SURFACE_3 = "#222732"       # selected rows, dropdowns
SURFACE_4 = "#2b313d"       # pressed / active chips

# --- Hairlines ---------------------------------------------------------- #
HAIRLINE = "#272c36"
HAIRLINE_STRONG = "#39414f"

# --- Ink hierarchy (all high-contrast on dark) -------------------------- #
INK = "#f3f6fc"             # headings, primary text
INK_MUTED = "#c2cad8"       # secondary text (still readable, not gray-on-gray)
INK_SUBTLE = "#8b94a6"      # tertiary / meta
INK_FAINT = "#5f6776"       # disabled / footnotes only

# --- Blue accent -------------------------------------------------------- #
PRIMARY = "#3b82f6"
PRIMARY_HOVER = "#5b9dff"
PRIMARY_PRESSED = "#2563eb"
PRIMARY_SOFT = "#16315c"    # tinted fill behind selected nav / accents

# --- Semantic ----------------------------------------------------------- #
SUCCESS = "#34d399"
WARNING = "#fbbf24"
DANGER = "#f87171"

# Backwards-compatible aliases (older modules import these names).
BG = CANVAS
SURFACE = SURFACE_1
BORDER = HAIRLINE
TEXT = INK
MUTED = INK_SUBTLE

# Build the stylesheet from the parts below.
from smartaccess.desktop.shell._qss import build_qss  # noqa: E402


def apply_theme(app: object) -> None:
    """Apply the dark QSS to a ``QApplication`` instance."""

    app.setStyleSheet(build_qss())
