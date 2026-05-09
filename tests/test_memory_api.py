from __future__ import annotations

import unittest

from memos_cli.backend.memory_api import MemoryAPI


class StubTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def request_json(self, method: str, path: str, **kwargs):
        self.calls.append((method, path, kwargs))
        return {
            "code": 0,
            "data": {
                "memory_detail_list": [],
                "preference_detail_list": [],
                "tool_memory_detail_list": [],
                "pages": 1,
            },
        }

    def request_first_json(self, method: str, paths: list[str], **kwargs):
        self.calls.append((method, paths[0], kwargs))
        return {"data": {"memories": []}}


class MemoryApiListTests(unittest.TestCase):
    def test_list_memories_caps_page_size_at_50(self) -> None:
        transport = StubTransport()
        api = MemoryAPI(transport)

        api.list_memories(user_id="user-123", page_size=100)

        _, _, kwargs = transport.calls[0]
        self.assertEqual(kwargs["json_body"]["size"], 50)

    def test_chat_prefers_product_complete_route(self) -> None:
        transport = StubTransport()
        api = MemoryAPI(transport)

        api.chat("hello", user_id="user-123", conversation_id="conv-1")

        method, path, kwargs = transport.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/chat")
        self.assertEqual(kwargs["json_body"]["query"], "hello")
        self.assertEqual(kwargs["json_body"]["user_id"], "user-123")
        self.assertEqual(kwargs["json_body"]["conversation_id"], "conv-1")
        self.assertNotIn("source", kwargs["json_body"])

    def test_chat_falls_back_to_product_complete_route(self) -> None:
        class FallbackTransport(StubTransport):
            def request_json(self, method: str, path: str, **kwargs):
                self.calls.append((method, path, kwargs))
                if path == "/chat":
                    raise RuntimeError("chat core route unavailable")
                return super().request_json(method, path, **kwargs)

            def request_first_json(self, method: str, paths: list[str], **kwargs):
                self.calls.append((method, paths[0], kwargs))
                return {
                    "code": 200,
                    "message": "Operation successful",
                    "data": "hello from product route",
                }

        transport = FallbackTransport()
        api = MemoryAPI(transport)

        result = api.chat(
            "hello",
            user_id="user-123",
            conversation_id="conv-1",
            mem_cube_id="cube-1",
            readable_cube_ids=["cube-1", "cube-2"],
            writable_cube_ids=["cube-1"],
            history=[{"role": "user", "content": "hi"}],
            filter={"topic": "prefs"},
            threshold=0.7,
            moscube=False,
        )

        self.assertEqual(transport.calls[0][1], "/chat")
        self.assertEqual(transport.calls[1][1], "/product/chat/complete")
        kwargs = transport.calls[1][2]
        self.assertEqual(kwargs["json_body"]["session_id"], "conv-1")
        self.assertEqual(kwargs["json_body"]["mem_cube_id"], "cube-1")
        self.assertEqual(kwargs["json_body"]["readable_cube_ids"], ["cube-1", "cube-2"])
        self.assertEqual(kwargs["json_body"]["writable_cube_ids"], ["cube-1"])
        self.assertEqual(kwargs["json_body"]["history"], [{"role": "user", "content": "hi"}])
        self.assertEqual(kwargs["json_body"]["filter"], {"topic": "prefs"})
        self.assertEqual(kwargs["json_body"]["threshold"], 0.7)
        self.assertFalse(kwargs["json_body"]["moscube"])
        self.assertEqual(result["answer"], "hello from product route")

    def test_create_knowledgebase_uses_official_route(self) -> None:
        transport = StubTransport()
        api = MemoryAPI(transport)

        api.create_knowledgebase("Project Docs", description="Internal docs")

        method, path, kwargs = transport.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/create/knowledgebase")
        self.assertEqual(kwargs["json_body"]["knowledgebase_name"], "Project Docs")
        self.assertEqual(kwargs["json_body"]["knowledgebase_description"], "Internal docs")

    def test_extract_memory_uses_extract_route(self) -> None:
        class ExtractTransport(StubTransport):
            def request_first_json(self, method: str, paths: list[str], **kwargs):
                self.calls.append((method, paths[0], kwargs))
                return {
                    "code": 0,
                    "data": [{"memory": "User likes coffee"}],
                }

        transport = ExtractTransport()
        api = MemoryAPI(transport)

        result = api.extract_memory("User likes coffee", user_id="user-123")

        method, path, kwargs = transport.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/extract/memory")
        self.assertEqual(kwargs["json_body"]["messages"], [{"role": "user", "content": "User likes coffee"}])
        self.assertEqual(kwargs["json_body"]["extraction_types"], ["memory", "preference"])
        self.assertEqual(kwargs["json_body"]["user_id"], "user-123")
        self.assertEqual(result["results"][0]["memory"], "User likes coffee")

    def test_rerank_documents_uses_official_route(self) -> None:
        class RerankTransport(StubTransport):
            def request_json(self, method: str, path: str, **kwargs):
                self.calls.append((method, path, kwargs))
                return {
                    "id": "rerank-1",
                    "model": "memos-reranker-0.6b",
                    "results": [
                        {
                            "index": 1,
                            "document": {"text": "用户偏好简洁的回复风格"},
                            "relevance_score": 0.98,
                        },
                        {
                            "index": 0,
                            "document": {"text": "用户喜欢打羽毛球"},
                            "relevance_score": 0.76,
                        },
                    ],
                }

        transport = RerankTransport()
        api = MemoryAPI(transport)

        result = api.rerank_documents(
            "用户有什么兴趣爱好",
            ["用户喜欢打羽毛球", "用户偏好简洁的回复风格"],
            top_n=1,
        )

        method, path, kwargs = transport.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/rerank")
        self.assertEqual(kwargs["json_body"]["query"], "用户有什么兴趣爱好")
        self.assertEqual(kwargs["json_body"]["documents"], ["用户喜欢打羽毛球", "用户偏好简洁的回复风格"])
        self.assertEqual(kwargs["json_body"]["model"], "memos-reranker-0.6b")
        self.assertEqual(kwargs["json_body"]["top_n"], 1)
        self.assertEqual(result["results"][0]["text"], "用户偏好简洁的回复风格")
        self.assertEqual(result["results"][0]["rank"], 1)

    def test_list_knowledgebases_uses_inferred_route(self) -> None:
        class KBTransport(StubTransport):
            def request_first_json(self, method: str, paths: list[str], **kwargs):
                self.calls.append((method, paths[0], kwargs))
                return {
                    "code": 0,
                    "data": [{"id": "kb-1", "knowledgebase_name": "Project Docs"}],
                }

        transport = KBTransport()
        api = MemoryAPI(transport)

        result = api.list_knowledgebases()

        method, path, kwargs = transport.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/get/knowledgebase")
        self.assertEqual(kwargs["json_body"], {})
        self.assertEqual(result[0]["id"], "kb-1")

    def test_add_knowledgebase_files_uses_official_route(self) -> None:
        transport = StubTransport()
        api = MemoryAPI(transport)

        api.add_knowledgebase_files(
            "kb-123",
            [{"content": "https://example.com/a.pdf"}],
        )

        method, path, kwargs = transport.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/add/knowledgebase-file")
        self.assertEqual(kwargs["json_body"]["knowledgebase_id"], "kb-123")
        self.assertEqual(kwargs["json_body"]["file"], [{"content": "https://example.com/a.pdf"}])

    def test_get_knowledgebase_file_uses_inferred_route(self) -> None:
        class KBTransport(StubTransport):
            def request_first_json(self, method: str, paths: list[str], **kwargs):
                self.calls.append((method, paths[0], kwargs))
                return {
                    "code": 0,
                    "data": {"id": "file-1", "name": "a.pdf", "status": "completed"},
                }

        transport = KBTransport()
        api = MemoryAPI(transport)

        result = api.get_knowledgebase_file("file-1")

        method, path, kwargs = transport.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/get/knowledgebase-file")
        self.assertEqual(kwargs["json_body"]["id"], "file-1")
        self.assertEqual(result["id"], "file-1")

    def test_delete_knowledgebase_files_uses_inferred_route(self) -> None:
        class KBTransport(StubTransport):
            def request_first_json(self, method: str, paths: list[str], **kwargs):
                self.calls.append((method, paths[0], kwargs))
                return {"code": 0, "message": "ok"}

        transport = KBTransport()
        api = MemoryAPI(transport)

        result = api.delete_knowledgebase_files("kb-123", ["file-1", "file-2"])

        method, path, kwargs = transport.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/delete/knowledgebase-file")
        self.assertEqual(kwargs["json_body"]["knowledgebase_id"], "kb-123")
        self.assertEqual(kwargs["json_body"]["file_ids"], ["file-1", "file-2"])
        self.assertTrue(result["deleted"])

    def test_delete_knowledgebase_files_can_omit_knowledgebase_id(self) -> None:
        class KBTransport(StubTransport):
            def request_first_json(self, method: str, paths: list[str], **kwargs):
                self.calls.append((method, paths[0], kwargs))
                return {"code": 0, "message": "ok"}

        transport = KBTransport()
        api = MemoryAPI(transport)

        api.delete_knowledgebase_files(None, ["file-1"])

        method, path, kwargs = transport.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/delete/knowledgebase-file")
        self.assertEqual(kwargs["json_body"], {"file_ids": ["file-1"]})

    def test_delete_knowledgebase_uses_inferred_route(self) -> None:
        class KBTransport(StubTransport):
            def request_first_json(self, method: str, paths: list[str], **kwargs):
                self.calls.append((method, paths[0], kwargs))
                return {"code": 0, "message": "ok"}

        transport = KBTransport()
        api = MemoryAPI(transport)

        result = api.delete_knowledgebase("kb-123")

        method, path, kwargs = transport.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/remove/knowledgebase")
        self.assertEqual(kwargs["json_body"]["knowledgebase_id"], "kb-123")
        self.assertTrue(result["deleted"])


if __name__ == "__main__":
    unittest.main()
