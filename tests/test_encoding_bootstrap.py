from __future__ import annotations

import io
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from memos_cli._encoding import configure_stdio_utf8


class _StreamStub:
    """Minimal ``sys.std*`` stand-in with a working ``reconfigure`` hook."""

    def __init__(self, *, encoding: str = "cp936") -> None:
        self.encoding = encoding
        self.errors = "strict"
        self.reconfigure_calls: list[dict] = []

    def reconfigure(self, *, encoding: str, errors: str) -> None:
        self.encoding = encoding
        self.errors = errors
        self.reconfigure_calls.append({"encoding": encoding, "errors": errors})


class _StreamWithoutReconfigure:
    """Older-style stream: no ``reconfigure`` but exposes a raw buffer."""

    def __init__(self) -> None:
        self.encoding = "cp936"
        self.buffer = io.BytesIO()


class ConfigureStdioUtf8Tests(unittest.TestCase):
    def test_reconfigure_is_called_with_utf8_when_available(self) -> None:
        stubs = {name: _StreamStub() for name in ("stdin", "stdout", "stderr")}

        with patch.multiple(
            sys,
            stdin=stubs["stdin"],
            stdout=stubs["stdout"],
            stderr=stubs["stderr"],
        ):
            configure_stdio_utf8()

        # stdin uses surrogateescape (lossless byte round-trip); output
        # streams use replace (display-only, can't destroy user data).
        self.assertEqual(
            stubs["stdin"].reconfigure_calls,
            [{"encoding": "utf-8", "errors": "surrogateescape"}],
        )
        self.assertEqual(stubs["stdin"].encoding, "utf-8")
        for name in ("stdout", "stderr"):
            self.assertEqual(
                stubs[name].reconfigure_calls,
                [{"encoding": "utf-8", "errors": "replace"}],
                msg=f"sys.{name} was not reconfigured to UTF-8/replace",
            )
            self.assertEqual(stubs[name].encoding, "utf-8")

    def test_falls_back_to_rewrap_when_reconfigure_missing(self) -> None:
        raw_stdout = _StreamWithoutReconfigure()

        # Capture ``sys.stdout`` while the patch is still active — reading it
        # after the ``with`` block exits would return the real interpreter's
        # stdout, not the TextIOWrapper installed by ``configure_stdio_utf8``.
        with patch.object(sys, "stdout", raw_stdout):
            with patch.object(sys, "stdin", _StreamStub()):
                with patch.object(sys, "stderr", _StreamStub()):
                    configure_stdio_utf8()
                    replaced = sys.stdout

        self.assertIsInstance(replaced, io.TextIOWrapper)
        self.assertEqual(replaced.encoding.lower(), "utf-8")
        self.assertEqual(replaced.errors, "replace")

    def test_sets_pythonioencoding_when_unset(self) -> None:
        environ = {k: v for k, v in os.environ.items() if k != "PYTHONIOENCODING"}
        with patch.dict(os.environ, environ, clear=True):
            configure_stdio_utf8(stream_names=())
            self.assertEqual(os.environ.get("PYTHONIOENCODING"), "utf-8")

    def test_preserves_existing_pythonioencoding(self) -> None:
        environ = {**os.environ, "PYTHONIOENCODING": "gbk"}
        with patch.dict(os.environ, environ, clear=True):
            configure_stdio_utf8(stream_names=())
            self.assertEqual(os.environ.get("PYTHONIOENCODING"), "gbk")

    def test_swallows_reconfigure_errors(self) -> None:
        class Angry:
            encoding = "cp936"

            def reconfigure(self, *, encoding: str, errors: str) -> None:
                raise OSError("stream is not seekable")

        angry = Angry()
        stub_out = _StreamStub()
        stub_err = _StreamStub()

        with patch.object(sys, "stdin", angry):
            with patch.object(sys, "stdout", stub_out):
                with patch.object(sys, "stderr", stub_err):
                    # Should not raise even though reconfigure() throws.
                    configure_stdio_utf8()

        # A hostile stdin must not abort processing of the remaining streams —
        # stdout and stderr must still get exactly one reconfigure call each.
        self.assertEqual(len(stub_out.reconfigure_calls), 1)
        self.assertEqual(len(stub_err.reconfigure_calls), 1)

    def test_idempotent_repeated_calls(self) -> None:
        """A second call must be a no-op on already-UTF-8 stdin, stdout, stderr."""
        stub_in = _StreamStub()
        stub_out = _StreamStub()
        stub_err = _StreamStub()
        with patch.object(sys, "stdin", stub_in):
            with patch.object(sys, "stdout", stub_out):
                with patch.object(sys, "stderr", stub_err):
                    configure_stdio_utf8()
                    configure_stdio_utf8()

        self.assertEqual(stub_in.encoding, "utf-8")
        # Second call short-circuits every stream via the
        # ``_is_already_utf8`` guard, not just stdin.
        self.assertEqual(len(stub_in.reconfigure_calls), 1)
        self.assertEqual(len(stub_out.reconfigure_calls), 1)
        self.assertEqual(len(stub_err.reconfigure_calls), 1)

    def test_idempotent_repeated_calls_fallback_path(self) -> None:
        """Second call on the rewrap path must not double-wrap the TextIOWrapper."""
        raw = _StreamWithoutReconfigure()
        with patch.object(sys, "stdout", raw):
            with patch.object(sys, "stdin", _StreamStub()):
                with patch.object(sys, "stderr", _StreamStub()):
                    configure_stdio_utf8()
                    first = sys.stdout
                    configure_stdio_utf8()
                    second = sys.stdout

        # Idempotent: the second call recognised ``first`` was already UTF-8
        # and left it in place instead of wrapping it a second time.
        self.assertIs(first, second)

    def test_missing_streams_are_skipped(self) -> None:
        # Some frozen environments do not attach ``sys.stdin``.
        with patch.object(sys, "stdin", None):
            with patch.object(sys, "stdout", _StreamStub()):
                with patch.object(sys, "stderr", _StreamStub()):
                    # Must not raise AttributeError on the missing stream.
                    configure_stdio_utf8()


class BootstrapImportSideEffectTests(unittest.TestCase):
    """Verify where the UTF-8 bootstrap runs — and, importantly, where it *doesn't*.

    The bootstrap must not fire when consumers merely ``import memos_cli`` as
    a library, but must still fire on the CLI entry-points
    (``memos_cli.__main__`` for ``python -m memos_cli`` and
    ``memos_cli.main`` for the ``memos`` console script).
    """

    _REPO_SRC = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"
    )

    def _env_without_pythonioencoding(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k != "PYTHONIOENCODING"}
        env["PYTHONPATH"] = os.pathsep.join(
            [self._REPO_SRC, env.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        return env

    def _run_and_capture_pythonioencoding(self, python_code: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-c", python_code],
            capture_output=True,
            text=True,
            env=self._env_without_pythonioencoding(),
            timeout=30,
        )

    def test_importing_memos_cli_does_not_touch_pythonioencoding(self) -> None:
        """``import memos_cli`` alone must remain side-effect-free (library use)."""
        result = self._run_and_capture_pythonioencoding(
            "import os, memos_cli; "
            "print(os.environ.get('PYTHONIOENCODING', ''))"
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout.strip(), "")

    def test_importing_memos_cli_main_sets_pythonioencoding(self) -> None:
        """The ``memos`` console-script entry (``memos_cli.main:app``) must bootstrap."""
        result = self._run_and_capture_pythonioencoding(
            "import os, memos_cli.main; "
            "print(os.environ.get('PYTHONIOENCODING', ''))"
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout.strip(), "utf-8")

    def test_importing_memos_cli_dunder_main_sets_pythonioencoding(self) -> None:
        """``python -m memos_cli`` path (``memos_cli.__main__``) must bootstrap."""
        result = self._run_and_capture_pythonioencoding(
            "import os, memos_cli.__main__; "
            "print(os.environ.get('PYTHONIOENCODING', ''))"
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout.strip(), "utf-8")


if __name__ == "__main__":
    unittest.main()
