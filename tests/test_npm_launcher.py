"""Regression tests for the npm launcher + PyInstaller onedir shipping layout.

Background
----------
Issue #10: the PyInstaller **onefile** bootloader allocates a SysV IPC
semaphore via ``semctl`` before the Python interpreter starts. Sandboxes
like Codex Desktop deny that syscall class, so ``memos`` aborts before
``memos_cli.__main__`` runs. The fix ships the CLI as a PyInstaller
**onedir** build — the bootloader dlopens the interpreter in-place, no
semaphore is ever touched.

This file covers the two surfaces that catch regressions cheaply:

1. ``bin/memos.js`` — the JS launcher that resolves the executable.
   Driven via a real ``node`` subprocess against a fabricated package
   root under ``tmp/``.
2. ``memos.spec`` — text asserts that fail if a future change reverts
   to onefile mode.

End-to-end packaging (actual ``python -m PyInstaller memos.spec``) and
live Codex Desktop reproduction are out of scope here — release CI
handles the first, a maintainer handles the second after release.
"""

from __future__ import annotations

import re
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_SRC = REPO_ROOT / "bin" / "memos.js"
SPEC_FILE = REPO_ROOT / "memos.spec"


def _node_available() -> bool:
    return shutil.which("node") is not None


class NpmLauncherResolutionTests(unittest.TestCase):
    """Drive ``bin/memos.js`` via a real ``node`` subprocess.

    We copy the launcher into a fabricated package root so the
    ``__dirname`` path resolution used by the launcher works exactly
    like it does after ``npm install``. Each test drops a stub
    executable (a shell script) into the layout it wants to exercise
    and checks stdout / stderr / exit code.
    """

    @classmethod
    def setUpClass(cls) -> None:
        if not _node_available():
            raise unittest.SkipTest("node not on PATH")
        if sys.platform == "win32":
            # Windows would need a .exe stub + PowerShell shim; the
            # POSIX branch already covers the resolution logic.
            raise unittest.SkipTest("launcher test uses POSIX shell stubs")

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.pkg_root = Path(self._tmp.name) / "pkg"
        (self.pkg_root / "bin").mkdir(parents=True)
        # Node walks up the tree looking for the closest package.json.
        # In some CI images the ancestor /tmp/package.json declares
        # "type": "module", which would flip the launcher into ESM
        # mode and blow up on `require`. Pin the module system here.
        (self.pkg_root / "package.json").write_text(
            '{"name": "memos-launcher-test", "type": "commonjs"}\n'
        )
        # Copy launcher verbatim so __dirname resolution matches prod.
        shutil.copy2(LAUNCHER_SRC, self.pkg_root / "bin" / "memos.js")

    def _write_stub(self, path: Path, exit_code: int = 0, marker: str = "") -> None:
        """Drop an executable shell script that prints ``marker`` and
        exits with ``exit_code``. Supports arbitrary ``"$@"`` args."""
        # Defensive: markers should be simple identifiers. If a future
        # caller passes something with shell metacharacters, printf %s
        # below still keeps the content safe, but flag it loudly.
        assert re.fullmatch(r"[A-Za-z0-9_]*", marker), (
            f"Unsafe marker with shell metacharacters: {marker!r}"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            textwrap.dedent(
                f"""\
                #!/usr/bin/env bash
                printf '%s\\n' '{marker}'
                echo "args=$*"
                exit {exit_code}
                """
            )
        )
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def _run_launcher(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["node", str(self.pkg_root / "bin" / "memos.js"), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_resolves_onedir_binary_when_present(self) -> None:
        """Onedir layout (``bin/memos/<exe>``) is picked when present.

        NOTE: We do **not** exercise a "onedir wins over a legacy file"
        priority contest here — on POSIX a directory named ``memos``
        and a regular file named ``memos`` cannot coexist under the
        same parent ``bin/``, so the launcher's priority ordering
        (onedir → legacy) is only observable when exactly one of the
        two exists. The legacy fallback path is covered separately by
        :meth:`test_falls_back_to_legacy_single_file`.
        """
        onedir_exe = self.pkg_root / "bin" / "memos" / "memos"
        legacy_exe = self.pkg_root / "bin" / "memos"

        self._write_stub(onedir_exe, exit_code=0, marker="ONEDIR_HIT")
        result = self._run_launcher("show", "config")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ONEDIR_HIT", result.stdout)
        self.assertIn("args=show config", result.stdout)
        # Regression guard: legacy file must NOT have been created by
        # the launcher itself (only postinstall touches disk). On
        # POSIX ``bin/memos`` here is the directory holding the onedir
        # binary, so ``is_file()`` correctly reports False.
        self.assertFalse(legacy_exe.is_file())

    def test_falls_back_to_legacy_single_file(self) -> None:
        """When onedir folder is absent, launcher uses ``bin/memos``."""
        legacy_exe = self.pkg_root / "bin" / "memos"
        self._write_stub(legacy_exe, exit_code=0, marker="LEGACY_HIT")

        result = self._run_launcher("--version")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("LEGACY_HIT", result.stdout)
        self.assertIn("args=--version", result.stdout)

    def test_missing_binary_reports_reinstall(self) -> None:
        """Neither layout present → clear error + exit 1."""
        result = self._run_launcher("show", "config")

        self.assertEqual(result.returncode, 1)
        self.assertIn("MemOS CLI binary is not installed", result.stderr)
        self.assertIn("Reinstall", result.stderr)

    def test_propagates_child_exit_code(self) -> None:
        """Child exit code (42) must reach the parent shell unchanged."""
        onedir_exe = self.pkg_root / "bin" / "memos" / "memos"
        self._write_stub(onedir_exe, exit_code=42, marker="EXIT42")

        result = self._run_launcher("simulate", "failure")

        self.assertEqual(result.returncode, 42)
        self.assertIn("EXIT42", result.stdout)


class SpecFileIsOnedirTests(unittest.TestCase):
    """Guard rails on ``memos.spec`` — trip if we ever revert to onefile.

    These are text asserts on the spec file rather than a PyInstaller
    build because building takes minutes and requires pyinstaller +
    the full build environment. The three assertions below capture
    the delta between onefile and onedir precisely.
    """

    @classmethod
    def setUpClass(cls) -> None:
        if not SPEC_FILE.exists():
            raise unittest.SkipTest(
                f"{SPEC_FILE} not found — run the build first"
            )
        cls.spec_text = SPEC_FILE.read_text()

    def test_spec_uses_collect(self) -> None:
        """Onedir requires a ``COLLECT(...)`` call — onefile has none."""
        self.assertIn(
            "COLLECT(",
            self.spec_text,
            "memos.spec must call COLLECT(...) for onedir mode — "
            "see issue #10.",
        )

    def test_exe_call_sets_exclude_binaries(self) -> None:
        """Onedir requires ``exclude_binaries=True`` on ``EXE(...)``."""
        self.assertIn(
            "exclude_binaries=True",
            self.spec_text,
            "memos.spec EXE(...) must set exclude_binaries=True for "
            "onedir mode — see issue #10.",
        )

    def test_spec_does_not_set_runtime_tmpdir(self) -> None:
        """``runtime_tmpdir=`` is a onefile-only argument."""
        self.assertNotIn(
            "runtime_tmpdir=",
            self.spec_text,
            "memos.spec must not set runtime_tmpdir (onefile-only). "
            "Reverting will re-introduce the semctl crash from #10.",
        )


if __name__ == "__main__":
    unittest.main()
