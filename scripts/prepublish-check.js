#!/usr/bin/env node

"use strict";

const fs = require("node:fs");
const path = require("node:path");

const pkg = require("../package.json");
const releaseAssets = require("../release-assets.json");

const rootDir = path.join(__dirname, "..");
const readmePath = path.join(rootDir, "README.md");
const issues = [];
const expectedTargets = ["darwin-arm64", "darwin-x64", "linux-x64", "windows-x64"];

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

if (
  !Array.isArray(releaseAssets.targets) ||
  JSON.stringify([...releaseAssets.targets].sort()) !== JSON.stringify([...expectedTargets].sort())
) {
  issues.push("release-assets.json must contain the complete four-platform target matrix.");
}

if (process.env.MEMOS_RELEASE_REQUIRE_RESOLVED_ASSETS === "1") {
  if (Number(releaseAssets.schema) !== 2 || releaseAssets.version !== pkg.version) {
    issues.push("live publish requires a schema 2 release-assets.json matching package.json version.");
  }
  if (!String(releaseAssets.public_base_url || "").startsWith("https://")) {
    issues.push("live publish requires an HTTPS release asset base URL.");
  }
  for (const target of expectedTargets) {
    const asset = releaseAssets.assets && releaseAssets.assets[target];
    const expectedName = `memos-${pkg.version}-${target}.tar.gz`;
    if (
      !asset ||
      asset.name !== expectedName ||
      !String(asset.url || "").startsWith("https://") ||
      !/^[a-f0-9]{64}$/i.test(String(asset.sha256 || ""))
    ) {
      issues.push(`live publish requires a versioned URL and SHA-256 for ${target}.`);
    }
  }
}

if (issues.length > 0) {
  console.error("Prepublish checks failed:");
  for (const issue of issues) {
    console.error(`- ${issue}`);
  }
  process.exit(1);
}

console.log(`Prepublish checks passed for ${pkg.name}@${pkg.version}.`);
