from __future__ import annotations

import unittest

from memos_cli.backend.normalizers import (
    normalize_add_response,
    normalize_chat_response,
    normalize_kb_create_response,
    normalize_kb_file_add_response,
    normalize_search_response,
)


class BackendNormalizationTests(unittest.TestCase):
    def test_normalize_search_response_flattens_memory_and_preference_lists(self) -> None:
        payload = {
            "data": {
                "memory_detail_list": [
                    {"memory_id": "mem-1", "memory_value": "User likes coffee", "score": 0.9}
                ],
                "preference_detail_list": [
                    {
                        "id": "pref-1",
                        "preference": "Prefers dark mode",
                        "preference_type": "explicit_preference",
                        "create_time": 1778232916444,
                        "relativity": 0.6278583,
                    }
                ],
            }
        }

        result = normalize_search_response(payload)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], "mem-1")
        self.assertEqual(result[0]["memory"], "User likes coffee")
        self.assertEqual(result[1]["id"], "pref-1")
        self.assertEqual(result[1]["memory"], "Prefers dark mode")
        self.assertEqual(result[1]["created_at"], 1778232916444)
        self.assertEqual(result[1]["score"], 0.6278583)

    def test_normalize_add_response_wraps_single_data_item(self) -> None:
        payload = {
            "data": {
                "memory_id": "mem-2",
                "memory_value": "User is allergic to peanuts",
            }
        }

        result = normalize_add_response(payload, original_text="User is allergic to peanuts")

        self.assertEqual(result["results"][0]["id"], "mem-2")
        self.assertEqual(result["results"][0]["memory"], "User is allergic to peanuts")

    def test_normalize_chat_response_extracts_answer_from_data_string(self) -> None:
        payload = {
            "code": 200,
            "message": "Operation successful",
            "data": "Hello from MemOS",
        }

        result = normalize_chat_response(payload, original_query="Say hi")

        self.assertEqual(result["answer"], "Hello from MemOS")
        self.assertEqual(result["query"], "Say hi")

    def test_normalize_kb_create_response_extracts_id(self) -> None:
        payload = {
            "code": 200,
            "message": "Operation successful",
            "data": {
                "id": "kb-123",
            },
        }

        result = normalize_kb_create_response(
            payload,
            name="Project Docs",
            description="Internal docs",
        )

        self.assertEqual(result["id"], "kb-123")
        self.assertEqual(result["knowledgebase_name"], "Project Docs")

    def test_normalize_kb_file_add_response_extracts_files(self) -> None:
        payload = {
            "code": 200,
            "data": [
                {"content": "https://example.com/a.pdf"},
                {"content": "https://example.com/b.pdf"},
            ],
        }

        result = normalize_kb_file_add_response(payload, knowledgebase_id="kb-123")

        self.assertEqual(result["knowledgebase_id"], "kb-123")
        self.assertEqual(len(result["files"]), 2)


if __name__ == "__main__":
    unittest.main()
