#!/usr/bin/env node

"use strict";

const { spawn } = require("child_process");
const { existsSync } = require("fs");
const path = require("path");

const exeName = process.platform === "win32" ? "memos.exe" : "memos";
const binDir = path.join(__dirname, "..", "bin");

// PyInstaller onedir layout ships an executable inside a `memos/` folder
// alongside its runtime dependencies. Prefer that path so the sandbox-safe
// build is used when it's present. Fall back to the legacy single-file
// path for users still on a pre-fix cached install (see issue #10).
const onedirBinary = path.join(binDir, "memos", exeName);
const legacyBinary = path.join(binDir, exeName);

let binaryPath = null;
if (existsSync(onedirBinary)) {
  binaryPath = onedirBinary;
} else if (existsSync(legacyBinary)) {
  binaryPath = legacyBinary;
}

if (binaryPath === null) {
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
