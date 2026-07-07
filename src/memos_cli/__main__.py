"""Allow running with `python -m memos_cli`.

The bootstrap in :mod:`memos_cli._encoding` runs as a side effect of
importing :mod:`memos_cli` (see :mod:`memos_cli.__init__`), so stdio is
already reconfigured to UTF-8 before ``memos_cli.main`` — and any Rich
``Console`` it constructs at module scope — is imported below.
"""
from memos_cli.main import app

if __name__ == "__main__":
    app()
