#!/usr/bin/env node

"use strict";

const fs = require("fs");
const { spawn } = require("child_process");
const path = require("path");

const exeName = process.platform === "win32" ? "memos.exe" : "memos";

// Prefer the onedir layout (bin/memos/<exe>). PyInstaller onedir was
// adopted in response to issue #10 — the onefile bootloader crashes
// with "semctl: Operation not permitted" inside sandboxes that block
// SysV IPC syscalls (Codex Desktop, hardened seccomp, containers
// without an IPC namespace).
const onedirBinary = path.join(__dirname, "memos", exeName);

// Fall back to the legacy single-file layout for cached pre-fix
// installs. Postinstall prunes the legacy file on upgrade, but a
// downgrade or a stale cache may still land here. Use __dirname
// directly (this file already lives in bin/) instead of a round-trip
// through "..", "bin" so the intent is obvious.
const legacyBinary = path.join(__dirname, exeName);

function isExecutableFile(filePath) {
  try {
    const stat = fs.statSync(filePath);
    if (!stat.isFile()) return false;
    if (process.platform !== "win32") {
      // Verify the execute bit is set so spawn does not fail with a
      // cryptic EACCES if the download landed without +x (e.g. a
      // regression in postinstall.js's makeExecutable step).
      fs.accessSync(filePath, fs.constants.X_OK);
    }
    return true;
  } catch (_) {
    return false;
  }
}

let binaryPath;
if (isExecutableFile(onedirBinary)) {
  binaryPath = onedirBinary;
} else if (isExecutableFile(legacyBinary)) {
  binaryPath = legacyBinary;
} else {
  console.error("MemOS CLI binary is not installed.");
  console.error("Reinstall the package to download the platform binary.");
  process.exit(1);
}

const child = spawn(binaryPath, process.argv.slice(2), {
  stdio: "inherit",
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(typeof code === "number" ? code : 1);
});

child.on("error", (error) => {
  console.error(`Failed to start MemOS CLI binary: ${error.message}`);
  process.exit(1);
});
