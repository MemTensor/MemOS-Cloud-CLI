from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from upload_release_assets import (
    live_contract_from_environment,
    runtime_contract,
    validate_live_contract,
)


class ReleaseAssetContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.targets = [
            "darwin-arm64",
            "darwin-x64",
            "linux-x64",
            "windows-x64",
        ]
        self.assets = [
            {
                "name": f"memos-1.0.7-{target}.tar.gz",
                "size": index + 100,
                "sha256": f"{index + 1:064x}",
                "md5": f"{index + 1:032x}",
            }
            for index, target in enumerate(self.targets)
        ]

    def test_runtime_contract_pins_every_asset_by_version_url_and_sha256(self) -> None:
        contract = runtime_contract(
            "v1.0.7",
            self.assets,
            "https://downloads.example.invalid/memos-cloud-cli/",
        )
        self.assertEqual(contract["schema"], 2)
        self.assertEqual(contract["version"], "1.0.7")
        self.assertEqual(sorted(contract["assets"]), sorted(self.targets))
        self.assertEqual(
            contract["assets"]["linux-x64"]["url"],
            "https://downloads.example.invalid/memos-cloud-cli/memos-1.0.7-linux-x64.tar.gz",
        )
        self.assertRegex(contract["assets"]["windows-x64"]["sha256"], r"^[a-f0-9]{64}$")

    def test_runtime_contract_fails_closed_on_missing_target_or_insecure_url(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "complete target matrix"):
            runtime_contract(
                "1.0.7",
                self.assets[:-1],
                "https://downloads.example.invalid/memos-cloud-cli",
            )
        with self.assertRaisesRegex(RuntimeError, "HTTPS"):
            runtime_contract(
                "1.0.7",
                self.assets,
                "http://downloads.example.invalid/memos-cloud-cli",
            )

    def test_live_configuration_comes_from_secrets_without_committing_endpoints(self) -> None:
        placeholder = {
            "bucket": "REPLACE_WITH_PRODUCTION_BUCKET",
            "endpoint": "https://REPLACE_WITH_PRODUCTION_OSS_ENDPOINT",
            "region": "REPLACE_WITH_PRODUCTION_REGION",
            "public_base_url": "https://example.invalid/memos-cloud-cli",
            "targets": self.targets,
        }
        env = {
            "OSS_BUCKET": "release-artifacts",
            "OSS_ENDPOINT": "https://oss.example.com",
            "OSS_REGION": "region-1",
            "MEMOS_CLI_OSS_PUBLIC_BASE_URL": "https://downloads.example.com/memos-cloud-cli",
        }
        with patch.dict(os.environ, env, clear=False):
            resolved = live_contract_from_environment(placeholder)
        validate_live_contract(resolved)
        self.assertEqual(resolved["bucket"], "release-artifacts")
        self.assertEqual(
            resolved["public_base_url"],
            "https://downloads.example.com/memos-cloud-cli",
        )


if __name__ == "__main__":
    unittest.main()
