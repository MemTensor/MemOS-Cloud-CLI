import assert from "node:assert/strict";
import test from "node:test";

import {
  expectedReleaseConfirmation,
  validateReleaseConfirmation,
} from "./validate-release-confirmation.mjs";

test("builds the exact publish confirmation phrase from a version", () => {
  assert.equal(expectedReleaseConfirmation("1.0.7"), "PUBLISH v1.0.7");
  assert.equal(expectedReleaseConfirmation("v1.0.7-beta.1"), "PUBLISH v1.0.7-beta.1");
});

test("does not require publish confirmation for dry runs", () => {
  assert.equal(
    validateReleaseConfirmation({
      version: "1.0.7",
      dryRun: "true",
      confirmation: "",
    }).ok,
    true,
  );
});

test("requires exact publish confirmation before a real release", () => {
  assert.equal(
    validateReleaseConfirmation({
      version: "1.0.7",
      dryRun: "false",
      confirmation: "",
    }).ok,
    false,
  );
  assert.equal(
    validateReleaseConfirmation({
      version: "1.0.7",
      dryRun: "false",
      confirmation: "PUBLISH 1.0.7",
    }).ok,
    false,
  );
  assert.equal(
    validateReleaseConfirmation({
      version: "1.0.7",
      dryRun: "false",
      confirmation: "PUBLISH v1.0.7",
    }).ok,
    true,
  );
});
