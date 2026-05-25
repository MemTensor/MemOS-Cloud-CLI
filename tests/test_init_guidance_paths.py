from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memos_cli.commands import init


class GuidancePathResolutionTests(unittest.TestCase):
    def test_global_guidance_uses_agent_home_for_standard_agents(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            supported = {
                "codex": root / ".codex" / "skills",
                "cursor": root / ".cursor" / "skills",
                "claude": root / ".claude" / "skills",
                "openclaw": root / ".openclaw" / "skills",
                "hermes": root / ".hermes" / "skills",
            }

            with patch.dict(init.SUPPORTED_SKILL_AGENTS, supported, clear=True):
                self.assertEqual(
                    init._resolve_guidance_files("cursor"),
                    [root / ".cursor" / "AGENTS.md"],
                )
                self.assertEqual(
                    init._resolve_guidance_files("claude"),
                    [root / ".claude" / "CLAUDE.md"],
                )
                self.assertEqual(
                    init._resolve_guidance_files("hermes"),
                    [root / ".hermes" / "AGENTS.md"],
                )

    def test_codex_guidance_honors_codex_home(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            codex_home = root / "custom-codex-home"

            with patch.dict(init.SUPPORTED_SKILL_AGENTS, {"codex": root / ".codex" / "skills"}, clear=True):
                with patch.dict("os.environ", {"CODEX_HOME": str(codex_home)}, clear=False):
                    self.assertEqual(
                        init._resolve_guidance_files("codex"),
                        [codex_home / "AGENTS.md"],
                    )

    def test_openclaw_guidance_updates_existing_agents_files_and_workspace_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            openclaw_home = root / ".openclaw"
            existing_paths = [
                openclaw_home / "workspace-codex" / "AGENTS.md",
                openclaw_home / "wiki" / "main" / "AGENTS.md",
                openclaw_home / "workspace" / "codex" / "AGENTS.md",
            ]
            for path in existing_paths:
                path.parent.mkdir(parents=True)
                path.write_text("existing\n")

            supported = {"openclaw": openclaw_home / "skills"}

            with patch.dict(init.SUPPORTED_SKILL_AGENTS, supported, clear=True):
                self.assertEqual(
                    init._resolve_guidance_files("openclaw"),
                    sorted([*existing_paths, openclaw_home / "workspace" / "AGENTS.md"]),
                )

    def test_openclaw_guidance_upserts_all_resolved_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            openclaw_home = root / ".openclaw"
            workspace_agents = openclaw_home / "workspace" / "AGENTS.md"
            nested_agents = openclaw_home / "workspace-codex" / "AGENTS.md"
            nested_agents.parent.mkdir(parents=True)
            nested_agents.write_text("existing\n")

            template = root / "agent_guidance.md"
            template.write_text("## Test Guidance\n")
            supported = {"openclaw": openclaw_home / "skills"}

            with patch.dict(init.SUPPORTED_SKILL_AGENTS, supported, clear=True):
                with patch.object(init, "_guidance_template_path", return_value=template):
                    written = init._install_agent_guidance("openclaw")

            self.assertEqual(written, sorted([workspace_agents, nested_agents]))
            for path in written:
                self.assertIn("## Test Guidance", path.read_text())


if __name__ == "__main__":
    unittest.main()
