"""Allow running with `python -m memos_cli`."""
# Force UTF-8 stdio before any other module import so CJK text is safe on
# Windows terminals whose ANSI code page is CP936/GBK.  See
# ``memos_cli.encoding_bootstrap`` for the full rationale.
from memos_cli.encoding_bootstrap import ensure_utf8_stdio

# NOTE: ``memos_cli.main`` *also* calls ``ensure_utf8_stdio()`` at module top
# level, and the idempotency guard makes the second call a cheap no-op.  We
# still fire it explicitly here so a future refactor (lazy import of ``main``,
# splitting subcommands, etc.) cannot silently strip the pre-import
# reconfigure.  Do not remove as "dead code" — the redundancy is the point.
ensure_utf8_stdio()

from memos_cli.main import app  # noqa: E402  (import after bootstrap is intentional)

if __name__ == "__main__":
    app()
