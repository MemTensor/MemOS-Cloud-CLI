#!/usr/bin/env node

"use strict";

const { spawn } = require("child_process");
const { existsSync } = require("fs");
const path = require("path");

const exeName = process.platform === "win32" ? "memos.exe" : "memos";
const binaryPath = path.join(__dirname, "..", "bin", exeName);

if (!existsSync(binaryPath)) {
  console.error("MemOS CLI binary is not installed.");
  console.error("Reinstall the package to download the platform binary.");
  process.exit(1);
}

// PEP 540 UTF-8 mode has to be requested before the Python interpreter starts,
// so we set it here in the child environment.  Without this, memos.exe on
// Simplified Chinese Windows binds sys.stdin/stdout/stderr to CP936/GBK and
// corrupts CJK text (issue #15).  Only set defaults so callers who deliberately
// pick a different encoding are respected.
const childEnv = Object.assign({}, process.env);
if (childEnv.PYTHONUTF8 === undefined) {
  childEnv.PYTHONUTF8 = "1";
}
if (childEnv.PYTHONIOENCODING === undefined) {
  childEnv.PYTHONIOENCODING = "utf-8";
}

const child = spawn(binaryPath, process.argv.slice(2), {
  stdio: "inherit",
  env: childEnv,
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
