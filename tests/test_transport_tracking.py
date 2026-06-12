from __future__ import annotations

import unittest
from unittest.mock import patch

from memos_cli.backend.transport import MemOSTransport


class TransportTrackingTests(unittest.TestCase):
    def test_request_adds_tracking_fields_to_json_object_body(self) -> None:
        transport = MemOSTransport(
            base_url="https://example.test/api/openmem/v1",
            api_key="test-key",
        )
        transport.framework = "codex"
        captured: dict = {}

        def fake_request(method, url, **kwargs):
            captured.update(kwargs)

            class Response:
                status_code = 200
                content = b"{}"
                text = "{}"

                def json(self):
                    return {}

                def raise_for_status(self):
                    return None

            return Response()

        with patch("requests.request", side_effect=fake_request):
            transport.request_json(
                "POST",
                "/add/message",
                json_body={"messages": [{"role": "user", "content": "hello"}]},
            )

        self.assertEqual(captured["json"]["source"], "cli-codex")
        self.assertEqual(captured["json"]["framework"], "codex")
        self.assertEqual(captured["headers"]["X-Source"], "cli-codex")
        self.assertEqual(captured["headers"]["X-Framework"], "codex")

    def test_request_adds_body_tracking_fields_when_headers_are_disabled(self) -> None:
        transport = MemOSTransport(
            base_url="https://example.test/api/openmem/v1",
            api_key="test-key",
        )
        transport.framework = "codex"
        captured: dict = {}

        def fake_request(method, url, **kwargs):
            captured.update(kwargs)

            class Response:
                status_code = 200
                content = b"{}"
                text = "{}"

                def json(self):
                    return {}

                def raise_for_status(self):
                    return None

            return Response()

        with patch("requests.request", side_effect=fake_request):
            transport.request_json(
                "POST",
                "/get/memory",
                json_body={"user_id": "u"},
                include_tracking_headers=False,
            )

        self.assertEqual(captured["json"]["source"], "cli-codex")
        self.assertEqual(captured["json"]["framework"], "codex")
        self.assertNotIn("X-Source", captured["headers"])
        self.assertNotIn("X-Framework", captured["headers"])


if __name__ == "__main__":
    unittest.main()
