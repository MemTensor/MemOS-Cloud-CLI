"""Tests for the npm launcher (`bin/memos.js`) and the onedir `memos.spec`.

The npm-installed CLI runs a JS launcher that resolves a PyInstaller
binary. Issue #10 required switching from onefile to onedir to avoid a
`semctl: Operation not permitted` crash inside sandboxes. These tests
exercise the launcher's binary resolution path (onedir preferred,
legacy single-file fallback, missing-binary error, exit-code
propagation) and guard `memos.spec` against a regression back to the
onefile layout.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER_SOURCE = REPO_ROOT / "bin" / "memos.js"
SPEC_FILE = REPO_ROOT / "memos.spec"


def _node_available() -> bool:
    return shutil.which("node") is not None


@unittest.skipUnless(_node_available(), "node is required to exercise the npm launcher")
class NpmLauncherResolutionTests(unittest.TestCase):
    """Spin up a fake npm package tree and drive `bin/memos.js` with `node`.

    A minimal shell stub stands in for the real PyInstaller binary so the
    test asserts the launcher's *resolution* logic without needing a
    real build artifact.
    """

    def setUp(self) -> None:
        if sys.platform == "win32":
            self.skipTest("shell-stub binaries only run on POSIX in this test")

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)

        # Fake package layout: <root>/bin/memos.js + optional binary drops.
        self.pkg_root = root / "pkg"
        self.bin_dir = self.pkg_root / "bin"
        self.onedir_dir = self.bin_dir / "memos"
        self.bin_dir.mkdir(parents=True)

        # A parent `package.json` with `"type": "module"` outside the temp
        # dir would cascade down and force node to treat `memos.js` as
        # ESM. Anchor the CommonJS type at the fake package root so the
        # launcher script (which uses `require`) parses correctly.
        (self.pkg_root / "package.json").write_text(
            '{"type":"commonjs"}\n', encoding="utf-8"
        )

        # Copy the real launcher into the fake package.
        self.launcher_path = self.bin_dir / "memos.js"
        shutil.copyfile(LAUNCHER_SOURCE, self.launcher_path)

    def _write_stub(self, target: Path, *, exit_code: int = 0, marker: str) -> None:
        """Write a POSIX shell stub that echoes a JSON marker + argv + exits."""
        target.parent.mkdir(parents=True, exist_ok=True)
        script = (
            "#!/bin/sh\n"
            f'printf \'{{"marker":"{marker}","argv":\'\n'
            'python3 -c "import json,sys; print(json.dumps(sys.argv[1:]))" "$@"\n'
            'printf \'}\\n\'\n'
            f"exit {exit_code}\n"
        )
        target.write_text(script, encoding="utf-8")
        mode = target.stat().st_mode
        target.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def _run_launcher(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["node", str(self.launcher_path), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_resolves_onedir_binary_when_present(self) -> None:
        onedir_binary = self.onedir_dir / "memos"
        self._write_stub(onedir_binary, marker="onedir")

        result = self._run_launcher("search", "python")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["marker"], "onedir")
        self.assertEqual(payload["argv"], ["search", "python"])

    def test_falls_back_to_legacy_single_file(self) -> None:
        # Only the legacy path exists (simulates cached npm install from
        # a pre-fix package version).
        legacy_binary = self.bin_dir / "memos"
        self._write_stub(legacy_binary, marker="legacy")

        result = self._run_launcher("--version")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["marker"], "legacy")
        self.assertEqual(payload["argv"], ["--version"])

    def test_missing_binary_reports_reinstall(self) -> None:
        result = self._run_launcher("status")

        self.assertEqual(result.returncode, 1)
        self.assertIn("MemOS CLI binary is not installed.", result.stderr)
        self.assertIn("Reinstall the package", result.stderr)

    def test_propagates_child_exit_code(self) -> None:
        onedir_binary = self.onedir_dir / "memos"
        self._write_stub(onedir_binary, marker="onedir", exit_code=42)

        result = self._run_launcher("delete", "mem_abc")

        self.assertEqual(result.returncode, 42, msg=result.stdout + result.stderr)


class SpecFileIsOnedirTests(unittest.TestCase):
    """Guard `memos.spec` against silent reversion to a onefile build."""

    def setUp(self) -> None:
        self.spec_text = SPEC_FILE.read_text(encoding="utf-8")

    def test_spec_uses_collect(self) -> None:
        # A onedir build is the pair `EXE(exclude_binaries=True) + COLLECT(...)`.
        # If either drops, the build silently reverts to onefile and the
        # semctl crash returns for sandboxed users.
        self.assertIn("COLLECT(", self.spec_text)
        self.assertIn("exclude_binaries=True", self.spec_text)

    def test_spec_does_not_set_runtime_tmpdir(self) -> None:
        # `runtime_tmpdir` is meaningful only for onefile EXE(). Its
        # presence would indicate a partial rollback.
        self.assertNotIn("runtime_tmpdir=", self.spec_text)


if __name__ == "__main__":
    unittest.main()
