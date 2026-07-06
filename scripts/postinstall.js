#!/usr/bin/env node

"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const https = require("node:https");
const { spawn } = require("node:child_process");

const pkg = require("../package.json");

if (process.env.MEMOS_INSTALL_SKIP_DOWNLOAD === "1" || process.env.MEMOS_INSTALL_SKIP_DOWNLOAD === "true") {
  process.exit(0);
}

const target = resolveTarget();
const assetName = `memos-${pkg.version}-${target}.tar.gz`;
const downloadUrl =
  process.env.MEMOS_BINARY_URL ||
  `https://memos-test.oss-cn-shanghai.aliyuncs.com/${assetName}`;

const installDir = path.join(__dirname, "..", "bin");
const archivePath = path.join(os.tmpdir(), assetName);
const binaryName = process.platform === "win32" ? "memos.exe" : "memos";
const onedirDir = path.join(installDir, "memos");
const onedirBinaryPath = path.join(onedirDir, binaryName);

fs.mkdirSync(installDir, { recursive: true });

if (!downloadUrl) {
  console.error("MEMOS_BINARY_URL is not set");
  process.exit(1);
}

// The archive now ships a top-level `memos/` folder (PyInstaller onedir).
// Clean out any prior onedir folder plus the legacy single-file drop from
// pre-fix installs before extraction so the two layouts do not collide.
cleanPreviousInstall(installDir, binaryName);

download(downloadUrl, archivePath)
  .then(() => extractArchive(archivePath, installDir))
  .then(() => clearQuarantine(onedirDir))
  .then(() => makeExecutable(onedirBinaryPath))
  .catch((error) => {
    console.error(`Failed to install MemOS CLI binary from ${downloadUrl}`);
    console.error(error.message);
    process.exit(1);
  });

function resolveTarget() {
  const platformMap = {
    darwin: "darwin",
    linux: "linux",
    win32: "windows",
  };
  const archMap = {
    arm64: "arm64",
    x64: "x64",
  };

  const platform = platformMap[process.platform];
  const arch = archMap[process.arch];

  if (!platform || !arch) {
    throw new Error(`Unsupported platform: ${process.platform}/${process.arch}`);
  }

  return `${platform}-${arch}`;
}

function cleanPreviousInstall(dir, binaryName) {
  // Remove a pre-existing onedir folder from a previous install so tar
  // never merges old and new contents.
  const previousOnedir = path.join(dir, "memos");
  if (fs.existsSync(previousOnedir) && fs.statSync(previousOnedir).isDirectory()) {
    fs.rmSync(previousOnedir, { recursive: true, force: true });
  }
  // Remove a legacy single-file drop from pre-fix installs so it does not
  // shadow the new folder layout or leave stale bytes on disk.
  const legacyFile = path.join(dir, binaryName);
  if (fs.existsSync(legacyFile) && fs.statSync(legacyFile).isFile()) {
    fs.rmSync(legacyFile, { force: true });
  }
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

function clearQuarantine(targetPath) {
  if (process.platform !== "darwin") {
    return Promise.resolve();
  }
  if (!fs.existsSync(targetPath)) {
    return Promise.resolve();
  }

  return new Promise((resolve) => {
    // `-r` recurses into the onedir folder so every bundled dylib / data
    // file loses the quarantine bit, not just the entry executable.
    const child = spawn("xattr", ["-dr", "com.apple.quarantine", targetPath], {
      stdio: "ignore",
    });

    child.on("exit", () => resolve());
    child.on("error", () => resolve());
  });
}
