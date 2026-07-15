from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import typer

from memos_cli.config import MemOSConfig, PlatformConfig, load_config
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
                    [root / ".hermes" / "SOUL.md"],
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

    def test_hermes_uninstall_guidance_removes_soul_md_and_legacy_agents_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            supported = {"hermes": root / ".hermes" / "skills"}
            soul_guidance = root / ".hermes" / "SOUL.md"
            legacy_guidance = root / ".hermes" / "AGENTS.md"
            for guidance in (soul_guidance, legacy_guidance):
                guidance.parent.mkdir(parents=True, exist_ok=True)
                guidance.write_text(
                    "keep before\n\n"
                    f"{init.GUIDANCE_START}\nmanaged\n{init.GUIDANCE_END}\n\n"
                    "keep after\n",
                    encoding="utf-8",
                )

            with patch.dict(init.SUPPORTED_SKILL_AGENTS, supported, clear=True):
                removed = init._uninstall_agent_guidance("hermes")

            self.assertEqual(removed, [soul_guidance, legacy_guidance])
            for guidance in removed:
                self.assertEqual(guidance.read_text(encoding="utf-8"), "keep before\n\nkeep after\n")

    def test_resolve_memos_bin_dir_prefers_current_command_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            current = root / "package" / "bin" / "memos"
            current.parent.mkdir(parents=True)
            current.write_text("#!/bin/sh\n", encoding="utf-8")

            other = root / "global" / "bin" / "memos"
            other.parent.mkdir(parents=True)
            other.write_text("#!/bin/sh\n", encoding="utf-8")

            with patch.object(init.sys, "argv", [str(current)]):
                with patch.object(init.shutil, "which", return_value=str(other)):
                    self.assertEqual(
                        init._resolve_memos_bin_dir(),
                        str(current.parent),
                    )

    def test_resolve_memos_bin_dir_uses_memos_from_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            memos = root / "custom-global" / "bin" / "memos"
            memos.parent.mkdir(parents=True)
            memos.write_text("#!/bin/sh\n", encoding="utf-8")

            def fake_which(name: str) -> str | None:
                return str(memos) if name == "memos" else None

            with patch.object(init.sys, "argv", ["memos"]):
                with patch.object(init.shutil, "which", side_effect=fake_which):
                    self.assertEqual(
                        init._resolve_memos_bin_dir(),
                        str(memos.parent),
                    )

    def test_resolve_memos_bin_dir_falls_back_to_npm_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            npm_prefix = root / "node-prefix"

            class Result:
                returncode = 0
                stdout = f"{npm_prefix}\n"

            def fake_which(name: str) -> str | None:
                return "/usr/bin/npm" if name == "npm" else None

            with patch.object(init.sys, "argv", ["memos"]):
                with patch.object(init.sys, "executable", "/usr/bin/python"):
                    with patch.object(init.shutil, "which", side_effect=fake_which):
                        with patch.object(init.subprocess, "run", return_value=Result()):
                            self.assertEqual(
                                init._resolve_memos_bin_dir(),
                                str(npm_prefix / "bin"),
                            )

    def test_init_skips_shell_path_when_memos_bin_dir_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.object(init.Path, "home", return_value=root):
                with patch.object(init, "_resolve_memos_bin_dir", return_value=None):
                    self.assertEqual(init._install_shell_path_entries("cursor"), [])

            self.assertFalse((root / ".bash_profile").exists())
            self.assertFalse((root / ".zshenv").exists())

    def test_init_installs_shell_path_block_for_any_agent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bin_dir = str(root / "node" / "bin")
            with patch.object(init.Path, "home", return_value=root):
                with patch.object(init, "_resolve_memos_bin_dir", return_value=bin_dir):
                    updated = init._install_shell_path_entries("cursor")

            self.assertEqual(updated, [root / ".bash_profile", root / ".zshenv"])
            for path in updated:
                content = path.read_text(encoding="utf-8")
                self.assertIn(init.SHELL_PATH_START, content)
                self.assertIn(init.SHELL_PATH_END, content)
                self.assertIn(f"{init.SHELL_MEMOS_BIN_VAR}={bin_dir}", content)
                self.assertIn(f'export PATH="${init.SHELL_MEMOS_BIN_VAR}:$PATH"', content)

    def test_init_shell_path_entries_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bin_dir = str(root / "node" / "bin")
            with patch.object(init.Path, "home", return_value=root):
                with patch.object(init, "_resolve_memos_bin_dir", return_value=bin_dir):
                    first = init._install_shell_path_entries("cursor")
                    second = init._install_shell_path_entries("claude")

            self.assertEqual(first, [root / ".bash_profile", root / ".zshenv"])
            self.assertEqual(second, [])
            for path in (root / ".bash_profile", root / ".zshenv"):
                content = path.read_text(encoding="utf-8")
                self.assertEqual(content.count(init.SHELL_PATH_START), 1)
                self.assertEqual(content.count(init.SHELL_PATH_END), 1)

    def test_init_skips_existing_shell_path_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bin_dir = str(root / "node" / "bin")
            bash_profile = root / ".bash_profile"
            bash_profile.parent.mkdir(parents=True, exist_ok=True)
            bash_profile.write_text(
                f'export PATH="{bin_dir}:$PATH"\n',
                encoding="utf-8",
            )

            with patch.object(init.Path, "home", return_value=root):
                with patch.object(init, "_resolve_memos_bin_dir", return_value=bin_dir):
                    updated = init._install_shell_path_entries("claude")

            self.assertEqual(updated, [root / ".zshenv"])
            self.assertEqual(
                bash_profile.read_text(encoding="utf-8"),
                f'export PATH="{bin_dir}:$PATH"\n',
            )

    def test_init_skips_existing_equivalent_shell_path_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bin_dir = str(root / ".npm-global" / "bin")
            bash_profile = root / ".bash_profile"
            zshenv = root / ".zshenv"
            bash_profile.write_text(
                f'export PATH="{bin_dir}:$PATH"\n',
                encoding="utf-8",
            )
            zshenv.write_text(
                'case ":$PATH:" in\n'
                "  *:${HOME}/.npm-global/bin:*) ;;\n"
                '  *) export PATH="${HOME}/.npm-global/bin:$PATH" ;;\n'
                "esac\n",
                encoding="utf-8",
            )

            with patch.object(init.Path, "home", return_value=root):
                with patch.object(init, "_resolve_memos_bin_dir", return_value=bin_dir):
                    updated = init._install_shell_path_entries("cursor")

            self.assertEqual(updated, [])
            self.assertNotIn(init.SHELL_PATH_START, bash_profile.read_text(encoding="utf-8"))
            self.assertNotIn(init.SHELL_PATH_START, zshenv.read_text(encoding="utf-8"))

    def test_uninstall_shell_path_helper_removes_blocks_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bash_profile = root / ".bash_profile"
            zshenv = root / ".zshenv"
            block = init._build_shell_path_block(str(root / "node" / "bin"))
            for path in (bash_profile, zshenv):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    "keep before\n\n"
                    f"{block}\n"
                    "keep after\n",
                    encoding="utf-8",
                )

            with patch.object(init.Path, "home", return_value=root):
                removed = init._uninstall_shell_path_entries("cursor")

            self.assertEqual(removed, [bash_profile, zshenv])
            for path in removed:
                self.assertEqual(path.read_text(encoding="utf-8"), "keep before\n\nkeep after\n")

    def test_uninstall_keeps_shell_path_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            supported = {"cursor": root / ".cursor" / "skills"}
            bash_profile = root / ".bash_profile"
            zshenv = root / ".zshenv"
            block = init._build_shell_path_block(str(root / "node" / "bin"))
            for path in (bash_profile, zshenv):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    "keep before\n\n"
                    f"{block}\n"
                    "keep after\n",
                    encoding="utf-8",
                )

            with patch.dict(init.SUPPORTED_SKILL_AGENTS, supported, clear=True):
                with patch.object(init.Path, "home", return_value=root):
                    init.uninstall_cmd(
                        agent="cursor",
                        yes=True,
                        remove_config=False,
                        remove_path=False,
                    )

            for path in (bash_profile, zshenv):
                self.assertIn(init.SHELL_PATH_START, path.read_text(encoding="utf-8"))

    def test_uninstall_removes_shell_path_only_with_path_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            supported = {"cursor": root / ".cursor" / "skills"}
            bash_profile = root / ".bash_profile"
            zshenv = root / ".zshenv"
            block = init._build_shell_path_block(str(root / "node" / "bin"))
            for path in (bash_profile, zshenv):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    "keep before\n\n"
                    f"{block}\n"
                    "keep after\n",
                    encoding="utf-8",
                )

            with patch.dict(init.SUPPORTED_SKILL_AGENTS, supported, clear=True):
                with patch.object(init.Path, "home", return_value=root):
                    init.uninstall_cmd(
                        agent="cursor",
                        yes=True,
                        remove_config=False,
                        remove_path=True,
                    )

            for path in (bash_profile, zshenv):
                self.assertNotIn(init.SHELL_PATH_START, path.read_text(encoding="utf-8"))
                self.assertEqual(path.read_text(encoding="utf-8"), "keep before\n\nkeep after\n")

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
                return ""

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
                                            with patch.object(
                                                init,
                                                "_install_shell_path_entries",
                                                return_value=[],
                                            ) as install_shell_path_entries:
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
            install_shell_path_entries.assert_called_once_with("cursor")

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

    def test_init_prompts_for_missing_api_key_in_interactive_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.yaml"
            config_file.write_text("existing\n", encoding="utf-8")
            existing_config = MemOSConfig(
                platform=PlatformConfig(
                    api_key="",
                    base_url="https://example.test/api",
                )
            )
            existing_config.defaults.user_id = "existing-user"
            existing_config.defaults.conversation_id = "existing-conversation"

            saved_configs: list[MemOSConfig] = []

            class Backend:
                def ping(self) -> None:
                    return None

            def fake_prompt(prompt: str, **kwargs):
                if "API key" in prompt:
                    return "entered-api-key"
                return ""

            def fake_save_config(config: MemOSConfig) -> None:
                saved_configs.append(config)

            with patch.object(init, "CONFIG_FILE", config_file):
                with patch.object(init, "load_config", return_value=existing_config):
                    with patch.object(init.sys.stdin, "isatty", return_value=True):
                        with patch.object(init.Prompt, "ask", side_effect=fake_prompt) as prompt:
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
                                            with patch.object(
                                                init,
                                                "_install_shell_path_entries",
                                                return_value=[],
                                            ):
                                                init.init_cmd(
                                                    api_key=None,
                                                    user_id=None,
                                                    conversation_id=None,
                                                    memos_plugin=False,
                                                    agent="cursor",
                                                )

            self.assertEqual(prompt.call_count, 3)
            self.assertEqual(saved_configs[0].platform.api_key, "entered-api-key")
            self.assertEqual(saved_configs[0].defaults.user_id, "existing-user")
            self.assertEqual(
                saved_configs[0].defaults.conversation_id,
                "existing-conversation",
            )

    def test_init_preserves_other_config_values_when_api_key_is_null(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_file = root / ".memos" / "config.yaml"
            config_file.parent.mkdir()
            config_file.write_text(
                "defaults:\n"
                "  conversation_id: existing-conversation\n"
                "  user_id: existing-user\n"
                "platform:\n"
                "  api_key: null\n"
                "  base_url: https://example.test/api\n",
                encoding="utf-8",
            )

            saved_configs: list[MemOSConfig] = []

            class Backend:
                def ping(self) -> None:
                    return None

            def fake_prompt(prompt: str, **kwargs):
                if "API key" in prompt:
                    return "entered-api-key"
                return ""

            def fake_save_config(config: MemOSConfig) -> None:
                saved_configs.append(config)

            with patch.object(init, "CONFIG_FILE", config_file):
                with patch.object(init, "load_config", load_config):
                    with patch("memos_cli.config.CONFIG_FILE", config_file):
                        with patch.object(init.sys.stdin, "isatty", return_value=True):
                            with patch.object(init.Prompt, "ask", side_effect=fake_prompt) as prompt:
                                with patch.object(init, "get_backend", return_value=Backend()):
                                    with patch.object(init, "save_config", side_effect=fake_save_config):
                                        with patch.object(
                                            init,
                                            "_install_bundled_skills",
                                            return_value=root / "skills" / "memos",
                                        ):
                                            with patch.object(
                                                init,
                                                "_install_agent_guidance",
                                                return_value=[root / "AGENTS.md"],
                                            ):
                                                with patch.object(
                                                    init,
                                                    "_install_shell_path_entries",
                                                    return_value=[],
                                                ):
                                                    init.init_cmd(
                                                        api_key=None,
                                                        user_id=None,
                                                        conversation_id=None,
                                                        memos_plugin=False,
                                                        agent="cursor",
                                                    )

            self.assertEqual(prompt.call_count, 3)
            self.assertEqual(saved_configs[0].platform.api_key, "entered-api-key")
            self.assertEqual(saved_configs[0].platform.base_url, "https://example.test/api")
            self.assertEqual(saved_configs[0].defaults.user_id, "existing-user")
            self.assertEqual(
                saved_configs[0].defaults.conversation_id,
                "existing-conversation",
            )

    def test_load_config_preserves_user_and_conversation_when_api_key_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.yaml"
            config_file.write_text(
                "defaults:\n"
                "  conversation_id: existing-conversation\n"
                "  user_id: existing-user\n"
                "platform:\n"
                "  base_url: https://example.test/api\n",
                encoding="utf-8",
            )

            with patch("memos_cli.config.CONFIG_FILE", config_file):
                config = load_config()

            self.assertEqual(config.platform.api_key, "")
            self.assertEqual(config.defaults.user_id, "existing-user")
            self.assertEqual(
                config.defaults.conversation_id,
                "existing-conversation",
            )

    def test_load_config_preserves_conversation_when_api_key_and_user_id_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.yaml"
            config_file.write_text(
                "defaults:\n"
                "  conversation_id: existing-conversation\n"
                "platform:\n"
                "  base_url: https://example.test/api\n",
                encoding="utf-8",
            )

            with patch("memos_cli.config.CONFIG_FILE", config_file):
                config = load_config()

            self.assertEqual(config.platform.api_key, "")
            self.assertEqual(config.defaults.user_id, "memos-cli")
            self.assertEqual(
                config.defaults.conversation_id,
                "existing-conversation",
            )


if __name__ == "__main__":
    unittest.main()
