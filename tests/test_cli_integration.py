from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mKJHABCDfsu]")
ROOT = Path(__file__).resolve().parents[1]


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def run_cli(
    args: list[str],
    *,
    home_dir: str | None = None,
    env_override: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env.pop("FORCE_COLOR", None)
    for key in list(env.keys()):
        if key.startswith("MEMOS_"):
            del env[key]
    if home_dir:
        env["HOME"] = home_dir
    if env_override:
        env.update(env_override)

    result = subprocess.run(
        [sys.executable, "-m", "memos_cli", *args],
        capture_output=True,
        text=True,
        env=env,
    )
    return subprocess.CompletedProcess(
        args=result.args,
        returncode=result.returncode,
        stdout=strip_ansi(result.stdout),
        stderr=strip_ansi(result.stderr),
    )


class CLIHelpTests(unittest.TestCase):
    def test_root_help(self) -> None:
        result = run_cli(["--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("memos", result.stdout)
        self.assertIn("init", result.stdout)
        self.assertIn("add", result.stdout)
        self.assertIn("list", result.stdout)
        self.assertIn("search", result.stdout)
        self.assertIn("chat", result.stdout)
        self.assertIn("kb", result.stdout)

    def test_init_help(self) -> None:
        result = run_cli(["init", "--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("--api-key", result.stdout)
        self.assertIn("--conversation-id", result.stdout)

    def test_add_help(self) -> None:
        result = run_cli(["add", "--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("--message", result.stdout)
        self.assertIn("--conversation-id", result.stdout)

    def test_search_help(self) -> None:
        result = run_cli(["search", "--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("--query", result.stdout)
        self.assertIn("--limit", result.stdout)

    def test_list_help(self) -> None:
        result = run_cli(["list", "--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("--user-id", result.stdout)
        self.assertIn("--limit", result.stdout)

    def test_chat_help(self) -> None:
        result = run_cli(["chat", "--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("--query", result.stdout)
        self.assertIn("--system-prompt", result.stdout)
        self.assertIn("--mem-cube-id", result.stdout)
        self.assertIn("--history", result.stdout)

    def test_config_help(self) -> None:
        result = run_cli(["config", "--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("show", result.stdout)
        self.assertIn("get", result.stdout)

    def test_kb_help(self) -> None:
        result = run_cli(["kb", "--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("create", result.stdout)

    def test_kb_create_help(self) -> None:
        result = run_cli(["kb", "create", "--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("--description", result.stdout)

    def test_kb_file_add_help(self) -> None:
        result = run_cli(["kb", "file", "add", "--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("Knowledge base ID", result.stdout)


class CLIIsolatedTests(unittest.TestCase):
    def test_config_show_on_clean_home(self) -> None:
        with tempfile.TemporaryDirectory() as home_dir:
            result = run_cli(["config", "show"], home_dir=home_dir)
            self.assertEqual(result.returncode, 0)
            self.assertIn("Base URL", result.stdout)
            self.assertIn("User ID", result.stdout)
            self.assertIn("Conversation ID", result.stdout)

    def test_config_set_get_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as home_dir:
            set_result = run_cli(
                ["config", "set", "defaults.user_id", "integration-user"],
                home_dir=home_dir,
            )
            self.assertEqual(set_result.returncode, 0)
            get_result = run_cli(
                ["config", "get", "defaults.user_id"],
                home_dir=home_dir,
            )
            self.assertEqual(get_result.returncode, 0)
            self.assertIn("integration-user", get_result.stdout)

    def test_add_without_text_fails(self) -> None:
        with tempfile.TemporaryDirectory() as home_dir:
            result = run_cli(["add"], home_dir=home_dir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No text provided", result.stdout + result.stderr)

    def test_search_without_query_fails(self) -> None:
        with tempfile.TemporaryDirectory() as home_dir:
            result = run_cli(["search"], home_dir=home_dir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No query provided", result.stdout + result.stderr)

    def test_chat_without_query_fails(self) -> None:
        with tempfile.TemporaryDirectory() as home_dir:
            result = run_cli(["chat"], home_dir=home_dir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No query provided", result.stdout + result.stderr)

    def test_chat_with_invalid_history_json_fails(self) -> None:
        with tempfile.TemporaryDirectory() as home_dir:
            result = run_cli(
                ["chat", "-q", "hello", "--history", "{bad"],
                home_dir=home_dir,
                env_override={"MEMOS_API_KEY": "test-key"},
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Invalid JSON for --history", result.stdout + result.stderr)

    def test_list_with_env_key_reaches_backend_layer(self) -> None:
        with tempfile.TemporaryDirectory() as home_dir:
            result = run_cli(
                ["list"],
                home_dir=home_dir,
                env_override={"MEMOS_API_KEY": "test-key"},
            )
            self.assertNotEqual(result.returncode, 0)
            combined = result.stdout + result.stderr
            self.assertNotIn("No API key configured", combined)

    def test_add_with_env_key_reaches_backend_layer(self) -> None:
        with tempfile.TemporaryDirectory() as home_dir:
            result = run_cli(
                ["add", "-m", "hello world"],
                home_dir=home_dir,
                env_override={"MEMOS_API_KEY": "test-key"},
            )
            self.assertNotEqual(result.returncode, 0)
            combined = result.stdout + result.stderr
            self.assertNotIn("No API key configured", combined)

    def test_chat_with_env_key_reaches_backend_layer(self) -> None:
        with tempfile.TemporaryDirectory() as home_dir:
            result = run_cli(
                ["chat", "-q", "hello"],
                home_dir=home_dir,
                env_override={"MEMOS_API_KEY": "test-key"},
            )
            self.assertNotEqual(result.returncode, 0)
            combined = result.stdout + result.stderr
            self.assertNotIn("No API key configured", combined)

    def test_kb_create_with_env_key_reaches_backend_layer(self) -> None:
        with tempfile.TemporaryDirectory() as home_dir:
            result = run_cli(
                ["kb", "create", "Project Docs"],
                home_dir=home_dir,
                env_override={"MEMOS_API_KEY": "test-key"},
            )
            self.assertNotEqual(result.returncode, 0)
            combined = result.stdout + result.stderr
            self.assertNotIn("No API key configured", combined)

    def test_kb_file_add_with_env_key_reaches_backend_layer(self) -> None:
        with tempfile.TemporaryDirectory() as home_dir:
            result = run_cli(
                ["kb", "file", "add", "kb-123", "https://example.com/a.pdf"],
                home_dir=home_dir,
                env_override={"MEMOS_API_KEY": "test-key"},
            )
            self.assertNotEqual(result.returncode, 0)
            combined = result.stdout + result.stderr
            self.assertNotIn("No API key configured", combined)

    def test_kb_file_add_rejects_unsupported_file_type_early(self) -> None:
        with tempfile.TemporaryDirectory() as home_dir:
            result = run_cli(
                ["kb", "file", "add", "kb-123", "https://example.com/page"],
                home_dir=home_dir,
                env_override={"MEMOS_API_KEY": "test-key"},
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Unsupported file type for knowledge base upload", result.stdout + result.stderr)

    def test_env_user_id_is_used_in_config_show(self) -> None:
        with tempfile.TemporaryDirectory() as home_dir:
            result = run_cli(
                ["config", "show"],
                home_dir=home_dir,
                env_override={"MEMOS_USER_ID": "env-user"},
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("env-user", result.stdout)

    def test_json_flag_preserves_envelope_shape_on_usage_errors_after_backend(self) -> None:
        with tempfile.TemporaryDirectory() as home_dir:
            config_dir = Path(home_dir) / ".memos"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_file = config_dir / "config.yaml"
            config_file.write_text(
                "platform:\n  api_key: test-key\n  base_url: https://example.invalid\n"
            )
            result = run_cli(["get", "--json", "mem_123"], home_dir=home_dir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("API error", result.stdout + result.stderr)

    def test_config_file_written_to_isolated_home(self) -> None:
        with tempfile.TemporaryDirectory() as home_dir:
            run_cli(["config", "set", "defaults.agent_id", "agent-42"], home_dir=home_dir)
            config_path = Path(home_dir) / ".memos" / "config.yaml"
            self.assertTrue(config_path.exists())
            self.assertIn("agent-42", config_path.read_text())


if __name__ == "__main__":
    unittest.main()
