"""MemOS CLI - Universal memory interface for AI agents."""
# Force UTF-8 stdio before anything else — Rich pins its Console encoding
# from ``sys.stdout`` at construction time, and command modules construct
# Console objects at import time.
from memos_cli._encoding import configure_stdio_utf8

configure_stdio_utf8()

__version__ = "1.0.4"
