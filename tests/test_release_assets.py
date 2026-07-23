from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.upload_release_assets import expected_assets, failure_payload, validate_assets, validate_live_contract


class ReleaseAssetContractTests(unittest.TestCase):
    def test_expected_matrix_matches_installer_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            names = [path.name for path in expected_assets("v1.2.3", Path(directory))]
        self.assertEqual(
            names,
            [
                "memos-1.2.3-darwin-arm64.tar.gz",
                "memos-1.2.3-darwin-x64.tar.gz",
                "memos-1.2.3-linux-x64.tar.gz",
                "memos-1.2.3-windows-x64.tar.gz",
            ],
        )

    def test_validation_requires_every_nonempty_asset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = expected_assets("1.2.3", root)
            for path in paths:
                path.write_bytes(b"archive")
            result = validate_assets("1.2.3", root)
            self.assertEqual(len(result), 4)
            self.assertEqual(result[0]["md5"], "888d0ee361af3603736f32131e7b20a2")
            paths[-1].unlink()
            with self.assertRaisesRegex(ValueError, "windows-x64"):
                validate_assets("1.2.3", root)

    def test_version_must_be_release_semver(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "invalid release version"):
                expected_assets("1.2", Path(directory))

    def test_failure_payload_preserves_three_sanitized_attempts(self) -> None:
        payload = failure_payload(
            "v1.2.3",
            "memos-1.2.3-linux-x64.tar.gz",
            ["attempt 1: timeout", "attempt 2: Bearer secret", "attempt 3: timeout"],
        )
        self.assertEqual(payload["phase"], "oss-upload")
        self.assertEqual(len(payload["attempts"]), 3)
        self.assertEqual(payload["attempts"][1]["message"], "attempt 2: Bearer ***")

    def test_live_contract_rejects_test_asset_targets(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "non-production OSS target"):
            validate_live_contract(
                {
                    "bucket": "release-testing-bucket",
                    "endpoint": "https://oss-cn-shanghai.aliyuncs.com",
                    "region": "cn-shanghai",
                    "public_base_url": "https://release-testing.example.invalid",
                    "targets": ["linux-x64"],
                },
            )

    def test_live_contract_requires_https_download_base(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "HTTPS"):
            validate_live_contract(
                {
                    "bucket": "memos-release",
                    "endpoint": "https://oss-cn-shanghai.aliyuncs.com",
                    "region": "cn-shanghai",
                    "public_base_url": "http://example.com/memos",
                    "targets": ["linux-x64"],
                },
            )

    def test_live_contract_rejects_placeholder_asset_targets(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "placeholder OSS settings"):
            validate_live_contract(
                {
                    "bucket": "REPLACE_WITH_PRODUCTION_BUCKET",
                    "endpoint": "https://REPLACE_WITH_PRODUCTION_OSS_ENDPOINT",
                    "region": "REPLACE_WITH_PRODUCTION_REGION",
                    "public_base_url": "https://example.invalid/memos-cloud-cli",
                    "targets": ["linux-x64"],
                },
            )


if __name__ == "__main__":
    unittest.main()
