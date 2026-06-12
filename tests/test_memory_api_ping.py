from __future__ import annotations

import unittest

from memos_cli.backend.memory_api import MemoryAPI
from memos_cli.backend.transport import APIError


class FailingTransport:
    def request_json(self, method: str, path: str, **kwargs):
        raise APIError(f"{method} {path} failed")


class MemoryAPIPingTests(unittest.TestCase):
    def test_ping_reports_last_fallback_error(self) -> None:
        api = MemoryAPI(FailingTransport())

        with self.assertRaises(APIError) as raised:
            api.ping()

        message = str(raised.exception)
        self.assertIn("Unable to reach MemOS API", message)
        self.assertIn("Last error: POST /search/memory failed", message)


if __name__ == "__main__":
    unittest.main()
