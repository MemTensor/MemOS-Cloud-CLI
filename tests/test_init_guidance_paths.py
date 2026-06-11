from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import typer

from memos_cli.config import MemOSConfig, PlatformConfig
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

    def test_uninstall_guidance_removes_managed_block_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            supported = {"cursor": root / ".cursor" / "skills"}
            guidance = root / ".cursor" / "AGENTS.md"
            guidance.parent.mkdir(parents=True)
            guidance.write_text(
                "keep before\n\n"
                f"{init.GUIDANCE_START}\nmanaged\n{init.GUIDANCE_END}\n\n"
                "keep after\n",
                encoding="utf-8",
            )

            with patch.dict(init.SUPPORTED_SKILL_AGENTS, supported, clear=True):
                removed = init._uninstall_agent_guidance("cursor")

            self.assertEqual(removed, [guidance])
            self.assertEqual(guidance.read_text(encoding="utf-8"), "keep before\n\nkeep after\n")

    def test_uninstall_guidance_keeps_empty_managed_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            supported = {"cursor": root / ".cursor" / "skills"}
            guidance = root / ".cursor" / "AGENTS.md"
            guidance.parent.mkdir(parents=True)
            guidance.write_text(
                f"{init.GUIDANCE_START}\nmanaged\n{init.GUIDANCE_END}\n",
                encoding="utf-8",
            )

            with patch.dict(init.SUPPORTED_SKILL_AGENTS, supported, clear=True):
                removed = init._uninstall_agent_guidance("cursor")

            self.assertEqual(removed, [guidance])
            self.assertTrue(guidance.exists())
            self.assertEqual(guidance.read_text(encoding="utf-8"), "")

    def test_remove_bundled_skills_removes_memos_memory_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            supported = {"cursor": root / ".cursor" / "skills"}
            installed = root / ".cursor" / "skills" / "memos" / "memos-memory"
            installed.mkdir(parents=True)
            (installed / "SKILL.md").write_text("skill\n", encoding="utf-8")

            with patch.dict(init.SUPPORTED_SKILL_AGENTS, supported, clear=True):
                removed = init._remove_bundled_skills("cursor")

            self.assertEqual(removed, [installed])
            self.assertFalse(installed.exists())
            self.assertFalse((root / ".cursor" / "skills" / "memos").exists())

    def test_uninstall_standalone_guidance_keeps_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "memos.md"
            path.write_text(f"{init.STANDALONE_FRONTMATTER}managed\n", encoding="utf-8")

            removed = init._remove_standalone_guidance(path)

            self.assertTrue(removed)
            self.assertTrue(path.exists())
            self.assertEqual(path.read_text(encoding="utf-8"), "")


class InitConfigResolutionTests(unittest.TestCase):
    def test_init_reuses_complete_existing_config_when_prompts_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.yaml"
            config_file.write_text("existing\n", encoding="utf-8")
            existing_config = MemOSConfig(
                platform=PlatformConfig(
                    api_key="existing-api-key",
                    base_url="https://example.test/api",
                )
            )
            existing_config.defaults.user_id = "existing-user"
            existing_config.defaults.conversation_id = "existing-conversation"

            prompts: list[str] = []
            saved_configs: list[MemOSConfig] = []

            class Backend:
                def ping(self) -> None:
                    return None

            def fake_prompt(prompt: str, **kwargs):
                prompts.append(prompt)
                return kwargs.get("default", "")

            def fake_save_config(config: MemOSConfig) -> None:
                saved_configs.append(config)

            with patch.object(init, "CONFIG_FILE", config_file):
                with patch.object(init, "load_config", return_value=existing_config):
                    with patch.object(init.sys.stdin, "isatty", return_value=True):
                        with patch.object(init.Prompt, "ask", side_effect=fake_prompt):
                            with patch.object(init, "get_backend", return_value=Backend()):
                                with patch.object(init, "save_config", side_effect=fake_save_config):
                                    with patch.object(
                                        init,
                                        "_install_bundled_skills",
                                        return_value=Path(temp_dir) / "skills" / "memos",
                                    ):
                                        with patch.object(
                                            init,
                                            "_install_agent_guidance",
                                            return_value=[Path(temp_dir) / "AGENTS.md"],
                                        ):
                                            init.init_cmd(
                                                api_key=None,
                                                user_id=None,
                                                conversation_id=None,
                                                memos_plugin=False,
                                                agent="cursor",
                                            )

            self.assertEqual(len(prompts), 3)
            self.assertEqual(saved_configs[0].platform.api_key, "existing-api-key")
            self.assertEqual(saved_configs[0].platform.base_url, "https://example.test/api")
            self.assertEqual(saved_configs[0].defaults.user_id, "existing-user")
            self.assertEqual(
                saved_configs[0].defaults.conversation_id,
                "existing-conversation",
            )
            self.assertEqual(saved_configs[0].defaults.framework, "cursor")

    def test_init_requires_api_key_when_no_complete_existing_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "missing-config.yaml"

            with patch.object(init, "CONFIG_FILE", config_file):
                with patch.object(init.Prompt, "ask") as prompt:
                    with self.assertRaises(typer.Exit) as raised:
                        init.init_cmd(
                            api_key=None,
                            user_id=None,
                            conversation_id=None,
                            memos_plugin=False,
                            agent="cursor",
                        )

            self.assertEqual(raised.exception.exit_code, 1)
            prompt.assert_not_called()


if __name__ == "__main__":
    unittest.main()
