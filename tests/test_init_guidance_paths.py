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

    def test_cli_guidance_excludes_plugin_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            template = Path(temp_dir) / "agent_guidance.md"
            template.write_text(
                "## MemOS CLI\n\n"
                "CLI guidance\n\n"
                "---\n\n"
                "## MemOS Plugin Mode\n\n"
                "Plugin guidance\n",
                encoding="utf-8",
            )

            with patch.object(init, "_guidance_template_path", return_value=template):
                content = init._build_agent_guidance("cursor")

        self.assertIn("## MemOS CLI", content)
        self.assertIn("CLI guidance", content)
        self.assertNotIn("## MemOS Plugin Mode", content)
        self.assertNotIn("Plugin guidance", content)

    def test_plugin_guidance_excludes_cli_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            template = Path(temp_dir) / "agent_guidance.md"
            template.write_text(
                "## MemOS CLI\n\n"
                "CLI guidance\n\n"
                "---\n\n"
                "## MemOS Plugin Mode\n\n"
                "Plugin guidance\n",
                encoding="utf-8",
            )

            with patch.object(init, "_guidance_template_path", return_value=template):
                content = init._build_plugin_agent_guidance("cursor")

        self.assertNotIn("## MemOS CLI", content)
        self.assertNotIn("CLI guidance", content)
        self.assertIn("## MemOS Plugin Mode", content)
        self.assertIn("Plugin guidance", content)

    def test_codex_prefix_rules_are_created(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            rules_file = Path(temp_dir) / ".codex" / "rules" / "default.rules"

            path, changed = init._ensure_codex_prefix_rules(rules_file)

            self.assertTrue(changed)
            self.assertEqual(path, rules_file)
            self.assertEqual(
                rules_file.read_text(encoding="utf-8").splitlines(),
                list(init.CODEX_PREFIX_RULES),
            )

    def test_codex_prefix_rules_are_idempotent_and_preserve_existing_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            rules_file = Path(temp_dir) / "default.rules"
            original = (
                "# keep this comment\n"
                'prefix_rule(pattern=["git", "status"], decision="allow")\n'
                'prefix_rule(pattern=["memos", "search"], decision="allow")\n'
            )
            rules_file.write_text(original, encoding="utf-8")

            _, first_changed = init._ensure_codex_prefix_rules(rules_file)
            after_first = rules_file.read_text(encoding="utf-8")
            _, second_changed = init._ensure_codex_prefix_rules(rules_file)
            after_second = rules_file.read_text(encoding="utf-8")

            self.assertTrue(first_changed)
            self.assertFalse(second_changed)
            self.assertEqual(after_first, after_second)
            self.assertTrue(after_first.startswith(original))
            for rule in init.CODEX_PREFIX_RULES:
                self.assertEqual(after_first.splitlines().count(rule), 1)

    def test_codex_prefix_rules_can_be_disabled(self) -> None:
        self.assertFalse(init._should_configure_codex_prefix_rules("cursor"))
        self.assertFalse(
            init._should_configure_codex_prefix_rules(
                "codex",
                no_codex_prefix_rules=True,
            )
        )
        with patch.dict("os.environ", {"MEMOS_SKIP_CODEX_RULES": "1"}, clear=False):
            self.assertFalse(init._should_configure_codex_prefix_rules("codex"))

        with patch.dict("os.environ", {"MEMOS_SKIP_CODEX_RULES": ""}, clear=False):
            self.assertTrue(init._should_configure_codex_prefix_rules("codex"))

    def test_codex_rules_file_honors_codex_home(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home = Path(temp_dir) / "codex-home"
            with patch.dict("os.environ", {"CODEX_HOME": str(codex_home)}, clear=False):
                self.assertEqual(
                    init._resolve_codex_rules_file(),
                    codex_home / "rules" / "default.rules",
                )


if __name__ == "__main__":
    unittest.main()
