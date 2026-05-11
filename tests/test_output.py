from __future__ import annotations

import unittest
from io import StringIO

from rich.console import Console

from memos_cli.output import format_memories_text, format_rerank_result


class OutputFormattingTests(unittest.TestCase):
    def test_format_memories_text_renders_type_and_created_columns(self) -> None:
        buffer = StringIO()
        console = Console(file=buffer, force_terminal=False, width=180)

        format_memories_text(
            console,
            [
                {
                    "id": "mem-1",
                    "memory": "User likes coffee",
                    "memory_type": "semantic_memory",
                    "created_at": "2026-05-08T10:30:00Z",
                    "score": 0.91,
                },
                {
                    "id": "pref-1",
                    "memory": "Prefers dark mode",
                    "memory_type": "explicit_preference",
                    "created_at": "2026-05-08T11:45:00Z",
                },
            ],
        )

        output = buffer.getvalue()
        self.assertIn("Type", output)
        self.assertIn("Created", output)
        self.assertIn("semantic memory", output)
        self.assertIn("explicit preference", output)
        self.assertIn("2026-05-08 10:30", output)
        self.assertIn("2026-05-08 11:45", output)

    def test_format_memories_text_supports_unix_ms_timestamp_and_score_alias(self) -> None:
        buffer = StringIO()
        console = Console(file=buffer, force_terminal=False, width=180)

        format_memories_text(
            console,
            [
                {
                    "id": "pref-1",
                    "memory": "用户喜欢吃香蕉",
                    "memory_type": "explicit_preference",
                    "created_at": 1778232916444,
                    "score": 0.6278583,
                }
            ],
        )

        output = buffer.getvalue()
        self.assertIn("2026-05-", output)
        self.assertIn("0.63", output)

    def test_format_rerank_result_renders_scores_and_documents(self) -> None:
        buffer = StringIO()
        console = Console(file=buffer, force_terminal=False, width=180)

        format_rerank_result(
            console,
            {
                "results": [
                    {
                        "rank": 1,
                        "text": "用户偏好简洁的回复风格",
                        "relevance_score": 0.9821,
                    },
                    {
                        "rank": 2,
                        "text": "用户喜欢打羽毛球",
                        "relevance_score": 0.7612,
                    },
                ]
            },
        )

        output = buffer.getvalue()
        self.assertIn("Found 2 rerank results", output)
        self.assertIn("0.98", output)
        self.assertIn("0.76", output)
        self.assertIn("用户偏好简洁的回复风格", output)
        self.assertIn("用户喜欢打羽毛球", output)


if __name__ == "__main__":
    unittest.main()
