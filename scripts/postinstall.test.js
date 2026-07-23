"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { SUPPORTED_TARGETS, resolveTarget } = require("./postinstall.js");

test("installer support exactly matches the release build contract", () => {
  assert.deepEqual([...SUPPORTED_TARGETS].sort(), [
    "darwin-arm64",
    "darwin-x64",
    "linux-x64",
    "windows-x64",
  ]);
  assert.equal(resolveTarget("darwin", "arm64"), "darwin-arm64");
  assert.equal(resolveTarget("darwin", "x64"), "darwin-x64");
  assert.equal(resolveTarget("linux", "x64"), "linux-x64");
  assert.equal(resolveTarget("win32", "x64"), "windows-x64");
  assert.throws(() => resolveTarget("linux", "arm64"), /Unsupported platform/);
  assert.throws(() => resolveTarget("win32", "arm64"), /Unsupported platform/);
});
