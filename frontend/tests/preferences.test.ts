import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_PREFERENCES,
  PREFERENCES_STORAGE_KEY,
  clampSpeedChallengeSeconds,
  loadPreferences,
  resetPreferences,
  savePreferences,
  type StorageLike,
} from "../lib/utils/preferences";

function createMemoryStorage(): StorageLike {
  const map = new Map<string, string>();
  return {
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => {
      map.set(key, value);
    },
    removeItem: (key) => {
      map.delete(key);
    },
  };
}

test("loadPreferences falls back to defaults and recovers from corrupt JSON", () => {
  const storage = createMemoryStorage();
  assert.deepEqual(loadPreferences(storage), DEFAULT_PREFERENCES);

  storage.setItem(PREFERENCES_STORAGE_KEY, "{broken-json");
  assert.deepEqual(loadPreferences(storage), DEFAULT_PREFERENCES);
});

test("savePreferences clamps speed timer and persists valid values", () => {
  const storage = createMemoryStorage();
  const saved = savePreferences(
    {
      default_exam_code: "ssc_cgl_tier_1",
      default_speed_challenge_seconds: 999,
      reduced_motion: true,
      compact_mode: false,
    },
    storage,
  );

  assert.equal(saved.default_exam_code, "ssc_cgl_tier_1");
  assert.equal(saved.default_speed_challenge_seconds, 300);
  assert.equal(saved.reduced_motion, true);

  assert.deepEqual(loadPreferences(storage), saved);
  assert.equal(clampSpeedChallengeSeconds(1), 5);
  assert.equal(clampSpeedChallengeSeconds("invalid"), 35);

  const reset = resetPreferences(storage);
  assert.deepEqual(reset, DEFAULT_PREFERENCES);
  assert.deepEqual(loadPreferences(storage), DEFAULT_PREFERENCES);
});
