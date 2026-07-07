from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memos_cli.config import MemOSConfig, load_config, save_config


class ConfigUtf8RoundTripTests(unittest.TestCase):
    """The config file must round-trip CJK values regardless of system codepage.

    On Windows, ``open()`` without ``encoding=`` falls back to the ANSI code
    page (CP936 / GBK on Chinese Windows). YAML values that contain CJK — for
    example a ``user_id`` that came in from a Chinese terminal — would then be
    silently corrupted when :func:`load_config` reads the file. These tests
    lock in ``encoding="utf-8"`` at both read and write time.
    """

    def test_load_config_reads_cjk_user_id_written_as_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.yaml"
            config_file.write_bytes(
                "defaults:\n"
                "  user_id: 测试用户\n"
                "  conversation_id: 会话-1\n"
                "platform:\n"
                "  api_key: token-x\n"
                "  base_url: https://example.test/api\n".encode("utf-8")
            )

            with patch("memos_cli.config.CONFIG_FILE", config_file):
                config = load_config()

            self.assertEqual(config.defaults.user_id, "测试用户")
            self.assertEqual(config.defaults.conversation_id, "会话-1")

    def test_save_config_writes_cjk_values_as_utf8_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.yaml"
            config = MemOSConfig()
            config.platform.api_key = "token-x"
            config.platform.base_url = "https://example.test/api"
            config.defaults.user_id = "测试用户"
            config.defaults.conversation_id = "会话-1"

            with patch("memos_cli.config.CONFIG_FILE", config_file):
                with patch("memos_cli.config.CONFIG_DIR", config_file.parent):
                    save_config(config)

            raw = config_file.read_bytes()
            self.assertIn("测试用户".encode("utf-8"), raw)
            self.assertIn("会话-1".encode("utf-8"), raw)

            # And a read-back must round-trip cleanly through UTF-8.
            with patch("memos_cli.config.CONFIG_FILE", config_file):
                reloaded = load_config()

            self.assertEqual(reloaded.defaults.user_id, "测试用户")
            self.assertEqual(reloaded.defaults.conversation_id, "会话-1")


if __name__ == "__main__":
    unittest.main()
