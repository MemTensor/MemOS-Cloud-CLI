#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");
const FILES = {
  package: path.join(ROOT, "package.json"),
  pyproject: path.join(ROOT, "pyproject.toml"),
  init: path.join(ROOT, "src", "memos_cli", "__init__.py"),
};

function normalizeVersion(value) {
  const version = String(value || "").trim().replace(/^v/, "");
  if (!/^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(version)) {
    throw new Error(`Invalid release version: ${value || "(empty)"}`);
  }
  return version;
}

function transformedContents(version, contents) {
  const pkg = JSON.parse(contents.package);
  pkg.version = version;
  const packageText = `${JSON.stringify(pkg, null, 2)}\n`;
  const pyprojectText = contents.pyproject.replace(
    /(\[project\][\s\S]*?\nversion\s*=\s*)"[^"]+"/,
    `$1"${version}"`,
  );
  const initText = contents.init.replace(/__version__\s*=\s*"[^"]+"/, `__version__ = "${version}"`);
  if (pyprojectText === contents.pyproject && !contents.pyproject.includes(`version = "${version}"`)) {
    throw new Error("Could not update [project].version in pyproject.toml");
  }
  if (initText === contents.init && !contents.init.includes(`__version__ = "${version}"`)) {
    throw new Error("Could not update __version__ in src/memos_cli/__init__.py");
  }
  return { package: packageText, pyproject: pyprojectText, init: initText };
}

function readContents() {
  return Object.fromEntries(Object.entries(FILES).map(([key, file]) => [key, fs.readFileSync(file, "utf8")]));
}

function syncVersion(version, { check = false } = {}) {
  const normalized = normalizeVersion(version);
  const current = readContents();
  const next = transformedContents(normalized, current);
  const changed = Object.keys(next).filter((key) => next[key] !== current[key]);
  if (check && changed.length) {
    throw new Error(`Version ${normalized} is not synchronized in: ${changed.join(", ")}`);
  }
  if (!check) {
    for (const key of changed) fs.writeFileSync(FILES[key], next[key], "utf8");
  }
  return { version: normalized, changed };
}

if (require.main === module) {
  try {
    const version = process.env.RELEASE_VERSION || process.argv.find((arg) => !arg.startsWith("--") && arg !== process.argv[0] && arg !== process.argv[1]);
    const result = syncVersion(version, { check: process.argv.includes("--check") });
    console.log(`${process.argv.includes("--check") ? "Verified" : "Synchronized"} MemOS CLI ${result.version}: ${result.changed.join(", ") || "already current"}`);
  } catch (error) {
    console.error(`::error::${error.message}`);
    process.exitCode = 1;
  }
}

module.exports = { normalizeVersion, syncVersion, transformedContents };
