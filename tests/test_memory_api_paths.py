from __future__ import annotations

import unittest

from memos_cli.backend.memory_api import MemoryAPI


class RecordingTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def request_json(self, method: str, path: str, **kwargs):
        self.calls.append((method, path, kwargs))
        return {"code": 0, "data": {}}


class MemoryAPIPathTests(unittest.TestCase):
    def test_extract_memory_uses_documented_endpoint_only(self) -> None:
        transport = RecordingTransport()
        api = MemoryAPI(transport)

        api.extract_memory([{"role": "user", "content": "likes coffee"}])

        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0][0], "POST")
        self.assertEqual(transport.calls[0][1], "/extract/memory")

    def test_search_memories_uses_documented_endpoint_only(self) -> None:
        transport = RecordingTransport()
        api = MemoryAPI(transport)

        api.search_memories("deployment", knowledgebase_ids=["base123"])

        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0][0], "POST")
        self.assertEqual(transport.calls[0][1], "/search/memory")
        self.assertEqual(transport.calls[0][2]["json_body"]["knowledgebase_ids"], ["base123"])


if __name__ == "__main__":
    unittest.main()
