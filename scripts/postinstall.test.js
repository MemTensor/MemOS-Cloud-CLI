"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {
  MAX_REDIRECTS,
  SUPPORTED_TARGETS,
  resolveAsset,
  resolveTarget,
  validateDownloadUrl,
} = require("./postinstall.js");

test("installer support exactly matches the release build contract", () => {
  assert.deepEqual([...SUPPORTED_TARGETS].sort(), [
    "darwin-arm64",
    "darwin-x64",
    "linux-x64",
    "windows-x64",
  ]);
  assert.equal(resolveTarget("darwin", "arm64"), "darwin-arm64");
  assert.equal(resolveTarget("darwin", "x64"), "darwin-x64");
  assert.equal(resolveTarget("linux", "x64"), "linux-x64");
  assert.equal(resolveTarget("win32", "x64"), "windows-x64");
  assert.throws(() => resolveTarget("linux", "arm64"), /Unsupported platform/);
  assert.throws(() => resolveTarget("win32", "arm64"), /Unsupported platform/);
});

test("installer resolves versioned assets only from a complete SHA-256 contract", () => {
  const checksum = "a".repeat(64);
  const contract = {
    schema: 2,
    version: "1.0.7",
    public_base_url: "https://downloads.example.invalid/memos-cloud-cli",
    targets: [...SUPPORTED_TARGETS],
    assets: {
      "linux-x64": {
        name: "memos-1.0.7-linux-x64.tar.gz",
        url: "https://downloads.example.invalid/memos-cloud-cli/memos-1.0.7-linux-x64.tar.gz",
        sha256: checksum,
      },
    },
  };
  assert.deepEqual(
    resolveAsset("linux-x64", { contract, packageVersion: "1.0.7", overrideUrl: "" }),
    {
      name: "memos-1.0.7-linux-x64.tar.gz",
      url: "https://downloads.example.invalid/memos-cloud-cli/memos-1.0.7-linux-x64.tar.gz",
      sha256: checksum,
    },
  );
  assert.throws(
    () => resolveAsset("linux-x64", { contract, packageVersion: "1.0.8", overrideUrl: "" }),
    /does not match npm package version/,
  );
  assert.throws(
    () => resolveAsset("darwin-arm64", { contract, packageVersion: "1.0.7", overrideUrl: "" }),
    /incomplete/,
  );
});

test("installer refuses insecure URLs and unverified overrides", () => {
  assert.equal(MAX_REDIRECTS, 5);
  assert.match(validateDownloadUrl("https://downloads.example.invalid/file"), /^https:/);
  assert.throws(() => validateDownloadUrl("http://downloads.example.invalid/file"), /non-HTTPS/);
  assert.throws(
    () => resolveAsset("linux-x64", {
      packageVersion: "1.0.7",
      overrideUrl: "https://downloads.example.invalid/custom.tar.gz",
      overrideSha256: "",
    }),
    /MEMOS_BINARY_SHA256 is required/,
  );
  assert.equal(
    resolveAsset("linux-x64", {
      packageVersion: "1.0.7",
      overrideUrl: "https://downloads.example.invalid/custom.tar.gz",
      overrideSha256: "b".repeat(64),
    }).sha256,
    "b".repeat(64),
  );
});
