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
