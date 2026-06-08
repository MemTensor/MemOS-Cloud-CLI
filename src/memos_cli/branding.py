"""Branding constants for MemOS CLI."""

# Color scheme
BRAND_COLOR = "blue"
ACCENT_COLOR = "cyan"
SUCCESS_COLOR = "green"
DIM_COLOR = "dim"

# Symbols
def _sym(unicode: str, fallback: str) -> str:
    """Return unicode symbol if supported, else fallback."""
    try:
        return unicode
    except Exception:
        return fallback
