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
// PyInstaller onedir layout: bin/memos/{memos,memos.exe} plus runtime deps.
const onedirRoot = path.join(installDir, "memos");
const onedirBinary = path.join(onedirRoot, binaryName);
// Pre-fix installs used a single-file `bin/memos` executable. It has to
// go before extracting the new folder, otherwise the folder can't be
// created at the same path.
const legacyBinary = path.join(installDir, binaryName);

fs.mkdirSync(installDir, { recursive: true });

if (!downloadUrl) {
  console.error("MEMOS_BINARY_URL is not set");
  process.exit(1);
}

download(downloadUrl, archivePath)
  .then(() => cleanPreviousInstall(onedirRoot, legacyBinary))
  .then(() => extractArchive(archivePath, installDir))
  .then(() => clearQuarantine(onedirRoot))
  .then(() => makeExecutable(onedirBinary))
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

function cleanPreviousInstall(onedirPath, legacyPath) {
  // Delete a prior onedir folder if one exists. Ignore ENOENT.
  try {
    fs.rmSync(onedirPath, { recursive: true, force: true });
  } catch (error) {
    // Best effort; extraction below will surface the real problem.
  }
  // Delete a legacy single-file binary that would otherwise collide
  // with `bin/memos/` on extraction (same path, different type).
  try {
    const stat = fs.lstatSync(legacyPath);
    if (stat.isFile() || stat.isSymbolicLink()) {
      fs.unlinkSync(legacyPath);
    }
  } catch (error) {
    if (error && error.code !== "ENOENT") {
      // Non-fatal; extraction below will fail loudly if this matters.
    }
  }
  return Promise.resolve();
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

  return new Promise((resolve) => {
    const child = spawn("xattr", ["-dr", "com.apple.quarantine", targetPath], {
      stdio: "ignore",
    });

    child.on("exit", () => resolve());
    child.on("error", () => resolve());
  });
}
