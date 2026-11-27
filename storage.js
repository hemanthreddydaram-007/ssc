/**
 * Persistent storage for custom & generated PYQ sets.
 * Uses IndexedDB so users can store N full previous-year papers without hitting
 * localStorage's 5 MB quota or a 20-set truncation cap, with automatic migration
 * and graceful fallback to localStorage when IndexedDB is unavailable.
 */

const DB_NAME = "ssc_chsl_35s_db_v1";
const DB_VERSION = 1;
const STORE_NAME = "customSets";
const LEGACY_CUSTOM_SETS_KEY = "ssc_chsl_custom_sets_v1";
const GEMINI_KEY_STORAGE = "ssc_chsl_gemini_key_v1";

function openDb() {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB unavailable"));
      return;
    }
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "id" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error || new Error("Failed to open IndexedDB"));
  });
}

function readLegacyLocalSets() {
  try {
    const raw = localStorage.getItem(LEGACY_CUSTOM_SETS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeLegacyLocalSets(sets) {
  try {
    localStorage.setItem(LEGACY_CUSTOM_SETS_KEY, JSON.stringify(sets));
  } catch {
    // Ignore storage quota errors cleanly
  }
}

/**
 * Loads all saved custom & generated sets sorted by creation order.
 * Automatically migrates any legacy localStorage sets into IndexedDB on first run.
 */
export async function loadCustomSets() {
  try {
    const db = await openDb();
    const existing = await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const store = tx.objectStore(STORE_NAME);
      const req = store.getAll();
      req.onsuccess = () => resolve(Array.isArray(req.result) ? req.result : []);
      req.onerror = () => reject(req.error);
    });

    const legacy = readLegacyLocalSets();
    if (legacy.length > 0) {
      const existingIds = new Set(existing.map((s) => s.id));
      const toMigrate = legacy.filter((s) => s && s.id && !existingIds.has(s.id));
      if (toMigrate.length > 0) {
        await new Promise((resolve, reject) => {
          const tx = db.transaction(STORE_NAME, "readwrite");
          const store = tx.objectStore(STORE_NAME);
          toMigrate.forEach((item, idx) => {
            store.put({
              ...item,
              createdAt: item.createdAt || Date.now() + idx
            });
          });
          tx.oncomplete = () => resolve();
          tx.onerror = () => reject(tx.error);
        });
        existing.push(...toMigrate);
      }
      try {
        localStorage.removeItem(LEGACY_CUSTOM_SETS_KEY);
      } catch {
        // Ignore cleanup errors
      }
    }

    db.close();
    return existing.sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0));
  } catch {
    return readLegacyLocalSets();
  }
}

/**
 * Saves one or more custom sets into IndexedDB (or localStorage fallback).
 */
export async function putCustomSets(newSets) {
  const list = Array.isArray(newSets) ? newSets : [newSets];
  if (list.length === 0) return;

  try {
    const db = await openDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      const store = tx.objectStore(STORE_NAME);
      list.forEach((item) => store.put(item));
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch {
    const existing = readLegacyLocalSets();
    const map = new Map(existing.map((s) => [s.id, s]));
    list.forEach((s) => map.set(s.id, s));
    writeLegacyLocalSets(Array.from(map.values()));
  }
}

/**
 * Deletes a single custom set by ID.
 */
export async function deleteCustomSet(setId) {
  try {
    const db = await openDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).delete(setId);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch {
    const remaining = readLegacyLocalSets().filter((s) => s.id !== setId);
    writeLegacyLocalSets(remaining);
  }
}

/**
 * Clears all custom & generated sets.
 */
export async function clearAllCustomSets() {
  try {
    const db = await openDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).clear();
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch {
    writeLegacyLocalSets([]);
  }
}

export function loadSavedGeminiKey() {
  try {
    return localStorage.getItem(GEMINI_KEY_STORAGE) || "";
  } catch {
    return "";
  }
}

export function saveGeminiKey(apiKey) {
  try {
    if (apiKey) {
      localStorage.setItem(GEMINI_KEY_STORAGE, apiKey);
    } else {
      localStorage.removeItem(GEMINI_KEY_STORAGE);
    }
  } catch {
    // Ignore storage errors
  }
}
