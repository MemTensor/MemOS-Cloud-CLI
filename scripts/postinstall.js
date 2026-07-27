#!/usr/bin/env node

"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const https = require("node:https");
const crypto = require("node:crypto");
const { spawn } = require("node:child_process");

const pkg = require("../package.json");
const releaseAssets = require("../release-assets.json");
const SUPPORTED_TARGETS = new Set(releaseAssets.targets);
const MAX_REDIRECTS = 5;
const SHA256_RE = /^[a-f0-9]{64}$/i;

function resolveTarget(platformName = process.platform, archName = process.arch) {
  const platformMap = {
    darwin: "darwin",
    linux: "linux",
    win32: "windows",
  };
  const archMap = {
    arm64: "arm64",
    x64: "x64",
  };

  const platform = platformMap[platformName];
  const arch = archMap[archName];

  const target = platform && arch ? `${platform}-${arch}` : "";
  if (!target || !SUPPORTED_TARGETS.has(target)) {
    throw new Error(`Unsupported platform: ${platformName}/${archName}`);
  }
  return target;
}

function validateDownloadUrl(value, baseUrl) {
  let parsed;
  try {
    parsed = baseUrl ? new URL(value, baseUrl) : new URL(value);
  } catch {
    throw new Error(`Invalid binary download URL: ${value}`);
  }
  if (parsed.protocol !== "https:") {
    throw new Error(`Refusing non-HTTPS binary download URL: ${parsed.protocol}`);
  }
  return parsed.toString();
}

function resolveAsset(target, {
  contract = releaseAssets,
  packageVersion = pkg.version,
  overrideUrl = process.env.MEMOS_BINARY_URL,
  overrideSha256 = process.env.MEMOS_BINARY_SHA256,
} = {}) {
  if (!SUPPORTED_TARGETS.has(target)) {
    throw new Error(`Unsupported release asset target: ${target}`);
  }
  const assetName = `memos-${packageVersion}-${target}.tar.gz`;
  if (overrideUrl) {
    const checksum = String(overrideSha256 || "").trim().toLowerCase();
    if (!SHA256_RE.test(checksum)) {
      throw new Error("MEMOS_BINARY_SHA256 is required when MEMOS_BINARY_URL overrides the signed release contract.");
    }
    return {
      name: assetName,
      url: validateDownloadUrl(overrideUrl),
      sha256: checksum,
    };
  }

  if (Number(contract.schema) !== 2 || String(contract.version || "") !== String(packageVersion)) {
    throw new Error(`Release asset contract does not match npm package version ${packageVersion}.`);
  }
  const asset = contract.assets && contract.assets[target];
  if (!asset || asset.name !== assetName || !SHA256_RE.test(String(asset.sha256 || ""))) {
    throw new Error(`Release asset contract is incomplete for ${target}.`);
  }
  return {
    name: assetName,
    url: validateDownloadUrl(asset.url || `${contract.public_base_url}/${assetName}`),
    sha256: String(asset.sha256).toLowerCase(),
  };
}

async function main() {
  if (process.env.MEMOS_INSTALL_SKIP_DOWNLOAD === "1" || process.env.MEMOS_INSTALL_SKIP_DOWNLOAD === "true") return;

  const target = resolveTarget();
  const asset = resolveAsset(target);
  const installDir = path.join(__dirname, "..", "bin");
  const temporaryDir = fs.mkdtempSync(path.join(os.tmpdir(), "memos-cli-"));
  const archivePath = path.join(temporaryDir, asset.name);
  const binaryName = process.platform === "win32" ? "memos.exe" : "memos";
  fs.mkdirSync(installDir, { recursive: true });

  try {
    await download(asset.url, archivePath, asset.sha256);
    await extractArchive(archivePath, installDir);
    await clearQuarantine(path.join(installDir, binaryName));
    makeExecutable(path.join(installDir, binaryName));
  } finally {
    try {
      if (fs.existsSync(archivePath)) fs.unlinkSync(archivePath);
      fs.rmdirSync(temporaryDir);
    } catch {
      // Cleanup failure must not hide the real download or extraction result.
    }
  }
}

function download(url, destination, expectedSha256, redirectCount = 0) {
  const downloadUrl = validateDownloadUrl(url);
  const expected = String(expectedSha256 || "").trim().toLowerCase();
  if (!SHA256_RE.test(expected)) {
    return Promise.reject(new Error("A valid SHA-256 checksum is required for the CLI binary."));
  }
  if (redirectCount > MAX_REDIRECTS) {
    return Promise.reject(new Error(`Binary download exceeded ${MAX_REDIRECTS} redirects.`));
  }
  return new Promise((resolve, reject) => {
    const request = https.get(downloadUrl, (response) => {
      if (response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
        response.resume();
        if (redirectCount >= MAX_REDIRECTS) {
          reject(new Error(`Binary download exceeded ${MAX_REDIRECTS} redirects.`));
          return;
        }
        let redirectUrl;
        try {
          redirectUrl = validateDownloadUrl(response.headers.location, downloadUrl);
        } catch (error) {
          reject(error);
          return;
        }
        download(redirectUrl, destination, expected, redirectCount + 1).then(resolve, reject);
        return;
      }

      if (response.statusCode !== 200) {
        response.resume();
        reject(new Error(`Unexpected status code: ${response.statusCode}`));
        return;
      }

      const hash = crypto.createHash("sha256");
      const file = fs.createWriteStream(destination);
      response.on("data", (chunk) => hash.update(chunk));
      response.pipe(file);
      file.on("finish", () => {
        file.close(() => {
          const actual = hash.digest("hex");
          if (actual !== expected) {
            try {
              fs.unlinkSync(destination);
            } catch {
              // The checksum failure remains the actionable error.
            }
            reject(new Error(`CLI binary SHA-256 mismatch: expected ${expected}, got ${actual}.`));
            return;
          }
          resolve();
        });
      });
      file.on("error", (error) => {
        response.destroy();
        reject(error);
      });
      response.on("error", reject);
    });

    request.on("error", reject);
  });
}

function extractArchive(archive, destination) {
  return new Promise((resolve, reject) => {
    const child = spawn("tar", ["-xzf", archive, "-C", destination], {
      stdio: "inherit",
    });

    child.on("exit", (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(`tar exited with code ${code}`));
    });

    child.on("error", reject);
  });
}

function makeExecutable(filePath) {
  if (process.platform !== "win32" && fs.existsSync(filePath)) {
    fs.chmodSync(filePath, 0o755);
  }
}

function clearQuarantine(filePath) {
  if (process.platform !== "darwin") {
    return Promise.resolve();
  }

  return new Promise((resolve) => {
    const child = spawn("xattr", ["-dr", "com.apple.quarantine", filePath], {
      stdio: "ignore",
    });

    child.on("exit", () => resolve());
    child.on("error", () => resolve());
  });
}

if (require.main === module) {
  main().catch((error) => {
    console.error(`Failed to install MemOS CLI binary: ${error.message}`);
    process.exitCode = 1;
  });
}

module.exports = {
  MAX_REDIRECTS,
  SUPPORTED_TARGETS,
  download,
  resolveAsset,
  resolveTarget,
  validateDownloadUrl,
};
