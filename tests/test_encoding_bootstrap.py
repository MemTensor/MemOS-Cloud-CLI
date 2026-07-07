"""Tests for :mod:`memos_cli.encoding_bootstrap`.

The bootstrap runs at import time on every Windows install, so it must be:

* idempotent — calling it repeatedly is a no-op;
* safe on non-Windows platforms — it must not corrupt stdio that is already
  UTF-8;
* resilient — a broken TextIOWrapper or a mock stream must not raise;
* pushing UTF-8 defaults into ``os.environ`` for child processes.

These tests exercise :func:`ensure_utf8_stdio` against fabricated stdio streams
so they run consistently in CI regardless of the host platform's real
``sys.stdout.encoding``.
"""

from __future__ import annotations

import io
import os
import sys
import unittest
from unittest.mock import patch


class EnsureUtf8StdioTests(unittest.TestCase):
    def setUp(self) -> None:
        # Reset the module-level cache so each test gets a fresh apply cycle.
        import memos_cli.encoding_bootstrap as bootstrap

        self.bootstrap = bootstrap
        bootstrap._APPLIED = False

        self._saved_stdin = sys.stdin
        self._saved_stdout = sys.stdout
        self._saved_stderr = sys.stderr
        self._saved_env = {
            "PYTHONIOENCODING": os.environ.get("PYTHONIOENCODING"),
            "PYTHONUTF8": os.environ.get("PYTHONUTF8"),
        }
        os.environ.pop("PYTHONIOENCODING", None)
        os.environ.pop("PYTHONUTF8", None)

    def tearDown(self) -> None:
        sys.stdin = self._saved_stdin
        sys.stdout = self._saved_stdout
        sys.stderr = self._saved_stderr
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.bootstrap._APPLIED = False

    # ------------------------------------------------------------------ utils

    def _make_stream(self, encoding: str) -> io.TextIOWrapper:
        buffer = io.BufferedWriter(io.BytesIO())
        return io.TextIOWrapper(buffer, encoding=encoding, errors="strict")

    def _make_input_stream(self, payload: bytes, encoding: str) -> io.TextIOWrapper:
        buffer = io.BufferedReader(io.BytesIO(payload))
        return io.TextIOWrapper(buffer, encoding=encoding, errors="strict")

    # ------------------------------------------------------------------ cases

    def test_reconfigures_gbk_stdout_to_utf8(self) -> None:
        gbk_stdout = self._make_stream("gbk")
        sys.stdout = gbk_stdout

        self.bootstrap.ensure_utf8_stdio()

        # After the bootstrap, sys.stdout speaks UTF-8 so CJK text writes cleanly.
        self.assertEqual(sys.stdout.encoding.lower().replace("-", ""), "utf8")
        sys.stdout.write("测试中文记忆存储")
        sys.stdout.flush()

    def test_reconfigures_gbk_stderr_to_utf8_with_replace_errors(self) -> None:
        gbk_stderr = self._make_stream("gbk")
        sys.stderr = gbk_stderr

        self.bootstrap.ensure_utf8_stdio()

        self.assertEqual(sys.stderr.encoding.lower().replace("-", ""), "utf8")
        # ``errors='replace'`` on stderr means a stray non-UTF-8 payload cannot
        # explode the CLI mid-error-message.
        self.assertEqual(sys.stderr.errors, "replace")

    def test_reconfigures_gbk_stdin_to_utf8(self) -> None:
        payload = "测试中文记忆存储\n".encode("utf-8")
        sys.stdin = self._make_input_stream(payload, "gbk")

        self.bootstrap.ensure_utf8_stdio()

        self.assertEqual(sys.stdin.encoding.lower().replace("-", ""), "utf8")
        self.assertEqual(sys.stdin.readline().rstrip("\n"), "测试中文记忆存储")

    def test_leaves_utf8_streams_untouched(self) -> None:
        utf8_stdout = self._make_stream("utf-8")
        sys.stdout = utf8_stdout

        self.bootstrap.ensure_utf8_stdio()

        self.assertIs(sys.stdout, utf8_stdout)

    def test_sets_env_defaults_for_child_processes(self) -> None:
        self.bootstrap.ensure_utf8_stdio()

        self.assertEqual(os.environ.get("PYTHONUTF8"), "1")
        self.assertEqual(os.environ.get("PYTHONIOENCODING"), "utf-8")

    def test_does_not_override_user_env_choices(self) -> None:
        os.environ["PYTHONUTF8"] = "0"
        os.environ["PYTHONIOENCODING"] = "latin-1"

        self.bootstrap.ensure_utf8_stdio()

        self.assertEqual(os.environ["PYTHONUTF8"], "0")
        self.assertEqual(os.environ["PYTHONIOENCODING"], "latin-1")

    def test_is_idempotent(self) -> None:
        gbk_stdout = self._make_stream("gbk")
        sys.stdout = gbk_stdout

        self.bootstrap.ensure_utf8_stdio()
        first = sys.stdout

        self.bootstrap.ensure_utf8_stdio()
        second = sys.stdout

        # Second call must be a no-op — the stream stays the same wrapper.
        self.assertIs(first, second)

    def test_reconfigure_failure_falls_back_to_buffer_wrap(self) -> None:
        class FakeStream:
            def __init__(self, buffer: io.BufferedWriter) -> None:
                self.encoding = "gbk"
                self.errors = "strict"
                self.line_buffering = False
                self.buffer = buffer

            def reconfigure(self, **_: object) -> None:
                raise io.UnsupportedOperation("cannot reconfigure")

        underlying = io.BufferedWriter(io.BytesIO())
        sys.stdout = FakeStream(underlying)

        self.bootstrap.ensure_utf8_stdio()

        # Fallback path swaps sys.stdout for a fresh TextIOWrapper on the same
        # buffer.  It must be UTF-8 and writable.
        self.assertIsInstance(sys.stdout, io.TextIOWrapper)
        self.assertEqual(sys.stdout.encoding.lower().replace("-", ""), "utf8")
        sys.stdout.write("测试")
        sys.stdout.flush()

    def test_missing_buffer_and_reconfigure_is_survivable(self) -> None:
        class BrokenStream:
            encoding = "gbk"

        sys.stdout = BrokenStream()

        # Must not raise even though we cannot fix this stream.
        self.bootstrap.ensure_utf8_stdio()

        # Still the broken stream — we swallowed the failure by design.
        self.assertIsInstance(sys.stdout, BrokenStream)

    def test_windows_console_cp_set_when_on_win32(self) -> None:
        calls: list[int] = []

        class FakeKernel32:
            def SetConsoleOutputCP(self, cp: int) -> None:
                calls.append(cp)

            def SetConsoleCP(self, cp: int) -> None:
                calls.append(cp)

        class FakeWindll:
            kernel32 = FakeKernel32()

        fake_ctypes = type(sys)("ctypes")  # a fresh module-like object
        fake_ctypes.windll = FakeWindll()

        with patch.object(sys, "platform", "win32"), patch.dict(
            sys.modules, {"ctypes": fake_ctypes}
        ):
            self.bootstrap.ensure_utf8_stdio()

        self.assertEqual(calls, [65001, 65001])

    def test_does_not_call_windows_console_cp_on_posix(self) -> None:
        # On non-Windows platforms the ctypes.windll dance is skipped.  If it
        # ran and reached ctypes.windll on Linux, importing would fail.  So the
        # bare fact that this call succeeds proves the guard works.
        self.assertNotEqual(sys.platform, "win32", "test assumes CI runs on POSIX")
        self.bootstrap.ensure_utf8_stdio()


if __name__ == "__main__":
    unittest.main()
