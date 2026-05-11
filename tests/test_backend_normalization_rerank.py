from __future__ import annotations

import unittest

from memos_cli.backend.normalizers import normalize_rerank_response


class BackendRerankNormalizationTests(unittest.TestCase):
    def test_normalize_rerank_response_extracts_nested_data_results(self) -> None:
        payload = {
            "code": 0,
            "data": {
                "id": "rerank-c7671b8d0d8bb16acc21e489b9317a11",
                "model": "memos-reranker-0.6b",
                "results": [
                    {
                        "index": 0,
                        "document": {"text": "用户喜欢打羽毛球"},
                        "relevance_score": 0.8084344863891602,
                    },
                    {
                        "index": 2,
                        "document": {"text": "用户周末常去爬山"},
                        "relevance_score": 0.5590996146202087,
                    },
                    {
                        "index": 1,
                        "document": {"text": "用户偏好简洁回复"},
                        "relevance_score": 0.5348607301712036,
                    },
                ],
            },
            "message": "ok",
        }

        result = normalize_rerank_response(
            payload,
            query="用户喜欢什么",
            documents=[
                "用户喜欢打羽毛球",
                "用户偏好简洁回复",
                "用户周末常去爬山",
            ],
        )

        self.assertEqual(len(result["results"]), 3)
        self.assertEqual(result["results"][0]["rank"], 1)
        self.assertEqual(result["results"][0]["text"], "用户喜欢打羽毛球")
        self.assertEqual(result["results"][1]["rank"], 2)
        self.assertEqual(result["results"][1]["text"], "用户周末常去爬山")
        self.assertEqual(result["results"][2]["rank"], 3)
        self.assertEqual(result["results"][2]["text"], "用户偏好简洁回复")


if __name__ == "__main__":
    unittest.main()
