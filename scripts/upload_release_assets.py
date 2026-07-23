#!/usr/bin/env python3
"""Validate and idempotently upload the CLI release matrix to Aliyun OSS."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def _clean_error(value: object) -> str:
    return re.sub(r"Bearer\s+\S+", "Bearer ***", str(value or ""), flags=re.IGNORECASE)[:600]


def failure_payload(version: str, asset_name: str, errors: list[str]) -> dict[str, Any]:
    clean_version = version.removeprefix("v")
    attempts = [
        {
            "attempt": index,
            "error_code": "OSS_UPLOAD",
            "message": _clean_error(error),
            "retryable": True,
        }
        for index, error in enumerate(errors[:3], start=1)
    ]
    return {
        "product_id": "memos-cloud-cli",
        "repository": os.getenv("GITHUB_REPOSITORY", "MemTensor/MemOS-Cloud-CLI"),
        "version": f"v{clean_version}",
        "phase": "oss-upload",
        "run_id": os.getenv("GITHUB_RUN_ID", f"v{clean_version}-cli"),
        "run_url": (
            f"https://github.com/{os.getenv('GITHUB_REPOSITORY', 'MemTensor/MemOS-Cloud-CLI')}/actions/runs/{os.getenv('GITHUB_RUN_ID')}"
            if os.getenv("GITHUB_RUN_ID")
            else ""
        ),
        "attempts": attempts,
        "final_error": _clean_error(f"{asset_name}: {errors[-1] if errors else 'unknown OSS failure'}"),
    }


def report_exhausted_failure(version: str, asset_name: str, errors: list[str]) -> None:
    token = os.getenv("DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN", "").strip()
    failure_url = os.getenv("DOC_AGENT_RELEASE_FAILURE_URL", "").strip()
    if not token or len(errors) < 3:
        return
    if not failure_url:
        print("::warning::DOC_AGENT_RELEASE_FAILURE_URL is not configured; skipping exhausted OSS retry report.")
        return
    request = urllib.request.Request(
        failure_url,
        data=json.dumps(failure_payload(version, asset_name, errors)).encode("utf-8"),
        headers={"content-type": "application/json", "authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status >= 300:
                raise RuntimeError(f"failure-report endpoint returned HTTP {response.status}")
        print(f"Reported exhausted OSS retries for {asset_name}")
    except Exception as exc:  # keep the original OSS failure as the workflow cause
        print(f"::warning::Failed to report exhausted OSS retries: {_clean_error(exc)}")


def load_contract() -> dict[str, Any]:
    return json.loads((ROOT / "release-assets.json").read_text(encoding="utf-8"))


def validate_live_contract(contract: dict[str, Any]) -> None:
    required = ("bucket", "endpoint", "region", "public_base_url", "targets")
    missing = [name for name in required if not contract.get(name)]
    if missing:
        raise RuntimeError(f"release-assets.json is missing required live release fields: {', '.join(missing)}")
    if not str(contract["public_base_url"]).startswith("https://"):
        raise RuntimeError("release-assets.json public_base_url must be an HTTPS URL for live releases")
    candidate = " ".join(str(contract.get(name, "")) for name in ("bucket", "endpoint", "public_base_url")).lower()
    if re.search(r"(^|[^a-z0-9])(test|testing|dev|staging)([^a-z0-9]|$)", candidate):
        raise RuntimeError(
            "release-assets.json appears to point at a non-production OSS target; "
            "update bucket/endpoint/public_base_url before a live CLI release"
        )
    if "replace_with" in candidate or "example.invalid" in candidate:
        raise RuntimeError(
            "release-assets.json still contains placeholder OSS settings; "
            "replace bucket/endpoint/region/public_base_url before a live CLI release"
        )


def expected_assets(version: str, assets_dir: Path) -> list[Path]:
    clean_version = version.removeprefix("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", clean_version):
        raise ValueError(f"invalid release version: {version}")
    contract = load_contract()
    return [assets_dir / f"memos-{clean_version}-{target}.tar.gz" for target in contract["targets"]]


def validate_assets(version: str, assets_dir: Path) -> list[dict[str, Any]]:
    paths = expected_assets(version, assets_dir)
    missing = [path.name for path in paths if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise ValueError(f"missing or empty release assets: {', '.join(missing)}")
    return [
        {
            "name": path.name,
            "path": str(path),
            "size": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "md5": hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest(),
        }
        for path in paths
    ]


def upload_assets(version: str, assets_dir: Path, *, dry_run: bool) -> dict[str, Any]:
    assets = validate_assets(version, assets_dir)
    result: dict[str, Any] = {"version": version.removeprefix("v"), "dry_run": dry_run, "assets": assets}
    if dry_run:
        return result

    try:
        import oss2
        from oss2.credentials import EnvironmentVariableCredentialsProvider
    except ImportError as exc:  # pragma: no cover - exercised on the release runner
        raise RuntimeError("oss2 is required for live OSS upload") from exc

    for name in ("OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_SECRET"):
        if not os.getenv(name):
            raise RuntimeError(f"{name} is required for live OSS upload")
    contract = load_contract()
    validate_live_contract(contract)
    auth = oss2.ProviderAuthV4(EnvironmentVariableCredentialsProvider())
    bucket = oss2.Bucket(
        auth,
        contract["endpoint"],
        contract["bucket"],
        region=contract["region"],
    )
    for asset in assets:
        key = asset["name"]
        errors: list[str] = []
        for attempt in range(1, 4):
            try:
                if bucket.object_exists(key):
                    remote = bucket.head_object(key)
                    remote_etag = str(remote.etag or "").strip('"').lower()
                    if int(remote.content_length) != int(asset["size"]) or remote_etag != asset["md5"]:
                        raise RuntimeError(f"OSS object {key} exists with different content; refusing overwrite")
                    asset["upload"] = "already-present-and-verified"
                    break
                bucket.put_object_from_file(key, asset["path"], headers={"x-oss-forbid-overwrite": "true"})
                remote = bucket.head_object(key)
                remote_etag = str(remote.etag or "").strip('"').lower()
                if int(remote.content_length) != int(asset["size"]) or remote_etag != asset["md5"]:
                    raise RuntimeError(f"OSS verification failed for {key}")
                asset["upload"] = "uploaded-and-verified"
                break
            except Exception as exc:
                errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
                if attempt == 3:
                    report_exhausted_failure(version, key, errors)
                    raise RuntimeError(f"OSS operation failed after three attempts for {key}: {'; '.join(errors)}") from exc
                time.sleep(attempt)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = upload_assets(args.version, args.assets_dir, dry_run=args.dry_run)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
