"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { normalizeVersion, transformedContents } = require("./sync-version.js");

test("normalizes a leading v and rejects non-semver values", () => {
  assert.equal(normalizeVersion("v1.2.3"), "1.2.3");
  assert.equal(normalizeVersion("1.2.3-beta.1"), "1.2.3-beta.1");
  assert.throws(() => normalizeVersion("latest"), /Invalid release version/);
});

test("updates package, pyproject, and Python runtime version together", () => {
  const next = transformedContents("1.2.3", {
    package: '{"name":"x","version":"1.0.0"}\n',
    pyproject: '[project]\nname = "x"\nversion = "1.0.0"\n',
    init: '__version__ = "1.0.0"\n',
  });
  assert.equal(JSON.parse(next.package).version, "1.2.3");
  assert.match(next.pyproject, /version = "1\.2\.3"/);
  assert.match(next.init, /__version__ = "1\.2\.3"/);
});
