"""Tests for Windows standard-stream compatibility."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from memos_cli.stdio import _configure_stream, configure_windows_stdio


class FakeStream:
    def __init__(self, *, is_terminal: bool) -> None:
        self.is_terminal = is_terminal
        self.calls: list[dict[str, str]] = []

    def isatty(self) -> bool:
        return self.is_terminal

    def reconfigure(self, **options: str) -> None:
        self.calls.append(options)


class StdioCompatibilityTests(unittest.TestCase):
    def test_redirected_stream_uses_utf8(self) -> None:
        stream = FakeStream(is_terminal=False)

        _configure_stream(stream)

        self.assertEqual(
            stream.calls,
            [{"errors": "backslashreplace", "encoding": "utf-8"}],
        )

    def test_terminal_keeps_native_encoding(self) -> None:
        stream = FakeStream(is_terminal=True)

        _configure_stream(stream)

        self.assertEqual(stream.calls, [{"errors": "backslashreplace"}])

    def test_missing_stream_is_ignored(self) -> None:
        _configure_stream(None)

    def test_configure_windows_stdio_reconfigures_redirected_stdin(self) -> None:
        stdin = FakeStream(is_terminal=False)
        stdout = FakeStream(is_terminal=False)
        stderr = FakeStream(is_terminal=False)

        with (
            patch("memos_cli.stdio.os.name", "nt"),
            patch("memos_cli.stdio.sys.stdin", stdin),
            patch("memos_cli.stdio.sys.stdout", stdout),
            patch("memos_cli.stdio.sys.stderr", stderr),
        ):
            configure_windows_stdio()

        expected = [{"errors": "backslashreplace", "encoding": "utf-8"}]
        self.assertEqual(stdin.calls, expected)
        self.assertEqual(stdout.calls, expected)
        self.assertEqual(stderr.calls, expected)

    def test_configure_windows_stdio_is_noop_off_windows(self) -> None:
        stdin = FakeStream(is_terminal=False)

        with (
            patch("memos_cli.stdio.os.name", "posix"),
            patch("memos_cli.stdio.sys.stdin", stdin),
        ):
            configure_windows_stdio()

        self.assertEqual(stdin.calls, [])


if __name__ == "__main__":
    unittest.main()
