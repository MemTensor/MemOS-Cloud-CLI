"""Allow running with `python -m memos_cli`."""
# Force UTF-8 stdio before any other module import so CJK text is safe on
# Windows terminals whose ANSI code page is CP936/GBK.  See
# ``memos_cli.encoding_bootstrap`` for the full rationale.
from memos_cli.encoding_bootstrap import ensure_utf8_stdio

ensure_utf8_stdio()

from memos_cli.main import app  # noqa: E402  (import after bootstrap is intentional)

if __name__ == "__main__":
    app()
