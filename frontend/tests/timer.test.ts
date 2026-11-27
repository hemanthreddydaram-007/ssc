import assert from "node:assert/strict";
import test from "node:test";

import {
  computeClockOffsetMs,
  computeRemainingMs,
  formatCountdownClock,
} from "../lib/utils/timer";

test("computeClockOffsetMs handles positive, negative, and invalid server timestamps", () => {
  const serverNow = "2026-11-27T10:00:00.000Z";
  const serverMs = Date.parse(serverNow);

  assert.equal(computeClockOffsetMs(serverNow, serverMs + 5000), 5000);
  assert.equal(computeClockOffsetMs(serverNow, serverMs - 3500), -3500);
  assert.equal(computeClockOffsetMs("not-a-timestamp", serverMs), 0);
});

test("computeRemainingMs stays accurate despite client clock skew and clamps at zero", () => {
  const serverNow = "2026-11-27T10:00:00.000Z";
  const expiresAt = "2026-11-27T10:00:35.000Z"; // 35s window

  // Client clock is 12 seconds ahead of server clock
  const clientAtSync = Date.parse(serverNow) + 12_000;
  const offset = computeClockOffsetMs(serverNow, clientAtSync);
  assert.equal(offset, 12_000);

  // Immediately after sync, remaining must still be 35_000 ms
  assert.equal(computeRemainingMs(expiresAt, offset, clientAtSync), 35_000);

  // 20 seconds later on client clock -> 15 seconds remaining
  assert.equal(
    computeRemainingMs(expiresAt, offset, clientAtSync + 20_000),
    15_000,
  );

  // Past expiry -> clamped at 0
  assert.equal(
    computeRemainingMs(expiresAt, offset, clientAtSync + 40_000),
    0,
  );

  // Missing or invalid expiry -> null
  assert.equal(computeRemainingMs(null, offset, clientAtSync), null);
  assert.equal(computeRemainingMs("invalid", offset, clientAtSync), null);
});

test("formatCountdownClock formats seconds, minutes, and hours", () => {
  assert.equal(formatCountdownClock(0), "00:00");
  assert.equal(formatCountdownClock(35_000), "00:35");
  assert.equal(formatCountdownClock(34_100), "00:35");
  assert.equal(formatCountdownClock(125_000), "02:05");
  assert.equal(formatCountdownClock(3_665_000), "1:01:05");
});
