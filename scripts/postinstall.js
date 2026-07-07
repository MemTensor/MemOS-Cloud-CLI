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
// Onedir layout: postinstall extracts a top-level "memos/" folder
// from the tarball, leaving the executable at bin/memos/<exe>. See
// issue #10 for why we moved off PyInstaller onefile.
const onedirRoot = path.join(installDir, "memos");
const onedirBinary = path.join(onedirRoot, binaryName);
// Legacy single-file path lingers on disk after upgrading from a
// pre-fix install; remove it before extracting so the new folder
// layout does not collide with it.
const legacyBinary = path.join(installDir, binaryName);

fs.mkdirSync(installDir, { recursive: true });

if (!downloadUrl) {
  console.error("MEMOS_BINARY_URL is not set");
  process.exit(1);
}

download(downloadUrl, archivePath)
  .then(() => pruneLegacyLayout())
  .then(() => extractArchive(archivePath, installDir))
  .then(() => {
    // Guard against a silent extraction (corrupt tarball, missing
    // top-level "memos/" folder, tar 0-exit on some platforms even
    // for empty archives). Without this check the downstream
    // clearQuarantine + makeExecutable both no-op silently and the
    // install would exit 0 with no usable binary.
    if (!fs.existsSync(onedirBinary)) {
      throw new Error(
        `Extraction succeeded but expected binary not found at ${onedirBinary}`
      );
    }
  })
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

function pruneLegacyLayout() {
  // Plain synchronous function: the .then(() => pruneLegacyLayout())
  // caller converts any thrown exception into a rejection so the
  // outer .catch handler still sees it. Wrapping the sync fs.*Sync
  // calls in a `new Promise((resolve) => ...)` executor with no
  // reject path silently swallows failures — see PR #14 review.

  // Remove a stale onedir folder from a previous install so tar
  // extraction is deterministic. If fs.rmSync throws synchronously
  // (e.g. EPERM on Windows if a file inside is locked, EACCES on
  // POSIX), let it propagate — extractArchive would fail on the same
  // locked path anyway, and a clear error message is preferable to a
  // silent no-op.
  if (fs.existsSync(onedirRoot)) {
    fs.rmSync(onedirRoot, { recursive: true, force: true });
  }
  // Remove a legacy single-file drop (pre-#10 layout) so the new
  // "memos/" folder can take its place on the filesystem. This one
  // is best-effort: the launcher still resolves the onedir path even
  // if the legacy file lingers, so filesystem quirks (locked file,
  // EACCES) should not fail the install — but do surface a warning
  // so users have a diagnostic trail.
  if (fs.existsSync(legacyBinary)) {
    try {
      const stat = fs.statSync(legacyBinary);
      if (stat.isFile()) {
        fs.unlinkSync(legacyBinary);
      }
    } catch (error) {
      console.warn(
        `Could not remove legacy binary at ${legacyBinary}: ${error.message}`
      );
    }
  }
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
    // Recursive: onedir ships a folder of dylibs, all of which the
    // Gatekeeper quarantine bit is stamped on.
    const child = spawn("xattr", ["-dr", "com.apple.quarantine", targetPath], {
      stdio: "ignore",
    });

    child.on("exit", () => resolve());
    child.on("error", () => resolve());
  });
}
