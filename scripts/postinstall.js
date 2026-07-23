#!/usr/bin/env node

"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const https = require("node:https");
const { spawn } = require("node:child_process");

const pkg = require("../package.json");
const releaseAssets = require("../release-assets.json");
const SUPPORTED_TARGETS = new Set(releaseAssets.targets);

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

async function main() {
  if (process.env.MEMOS_INSTALL_SKIP_DOWNLOAD === "1" || process.env.MEMOS_INSTALL_SKIP_DOWNLOAD === "true") return;

  const target = resolveTarget();
  const assetName = `memos-${pkg.version}-${target}.tar.gz`;
  const downloadUrl = process.env.MEMOS_BINARY_URL || `${releaseAssets.public_base_url}/${assetName}`;
  const installDir = path.join(__dirname, "..", "bin");
  const archivePath = path.join(os.tmpdir(), assetName);
  const binaryName = process.platform === "win32" ? "memos.exe" : "memos";
  fs.mkdirSync(installDir, { recursive: true });

  await download(downloadUrl, archivePath);
  await extractArchive(archivePath, installDir);
  await clearQuarantine(path.join(installDir, binaryName));
  makeExecutable(path.join(installDir, binaryName));
}

function download(url, destination) {
  return new Promise((resolve, reject) => {
    const request = https.get(url, (response) => {
      if (response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
        response.resume();
        download(response.headers.location, destination).then(resolve, reject);
        return;
      }

      if (response.statusCode !== 200) {
        response.resume();
        reject(new Error(`Unexpected status code: ${response.statusCode}`));
        return;
      }

      const file = fs.createWriteStream(destination);
      response.pipe(file);
      file.on("finish", () => file.close(resolve));
      file.on("error", reject);
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

module.exports = { SUPPORTED_TARGETS, resolveTarget };
