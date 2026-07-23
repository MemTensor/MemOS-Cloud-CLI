#!/usr/bin/env node

"use strict";

const fs = require("node:fs");
const path = require("node:path");

const pkg = require("../package.json");

const rootDir = path.join(__dirname, "..");
const readmePath = path.join(rootDir, "README.md");
const issues = [];

if (!pkg.name || !pkg.name.startsWith("@memtensor/")) {
  issues.push("package.json name must use the @memtensor/ scope.");
}

if (!pkg.version || !/^\d+\.\d+\.\d+(-[\w.-]+)?$/.test(pkg.version)) {
  issues.push("package.json version must be a valid semver string.");
}

if (!pkg.bin || !pkg.bin.memos) {
  issues.push("package.json must define the memos bin entry.");
}

if (
  !Array.isArray(pkg.files) ||
  !pkg.files.includes("bin/memos.js") ||
  !pkg.files.includes("scripts/postinstall.js") ||
  !pkg.files.includes("release-assets.json")
) {
  issues.push("package.json files must include only the runtime npm wrapper files.");
}

if (!fs.existsSync(readmePath)) {
  issues.push("README.md is missing at the repository root.");
}

if (issues.length > 0) {
  console.error("Prepublish checks failed:");
  for (const issue of issues) {
    console.error(`- ${issue}`);
  }
  process.exit(1);
}

console.log(`Prepublish checks passed for ${pkg.name}@${pkg.version}.`);
