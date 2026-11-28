import assert from "node:assert/strict";
import test from "node:test";

import {
  ApiError,
  apiFetch,
  extractErrorMessage,
  shouldRetryColdStartRequest,
} from "../lib/api/client";

test("extractErrorMessage handles FastAPI string detail and Pydantic validation arrays", () => {
  const strRes = extractErrorMessage(
    {
      detail: "Duplicate document detected",
      code: "DUPLICATE_DOCUMENT",
      existing_document_id: "doc-123",
    },
    "Fallback",
  );
  assert.equal(strRes.message, "Duplicate document detected");
  assert.equal(strRes.objectPayload?.code, "DUPLICATE_DOCUMENT");
  assert.equal(strRes.objectPayload?.existing_document_id, "doc-123");

  const pydanticRes = extractErrorMessage(
    {
      detail: [{ loc: ["body", "title"], msg: "Field required" }],
    },
    "Fallback",
  );
  assert.equal(pydanticRes.message, "Field required");

  const emptyRes = extractErrorMessage(null, "Default error");
  assert.equal(emptyRes.message, "Default error");
  assert.equal(emptyRes.objectPayload, null);
});

test("ApiError preserves status, code, and existing_document_id", () => {
  const err = new ApiError("Duplicate", 409, {
    code: "DUPLICATE_DOCUMENT",
    existing_document_id: "abc-999",
  });
  assert.equal(err.status, 409);
  assert.equal(err.code, "DUPLICATE_DOCUMENT");
  assert.equal(err.existingDocumentId, "abc-999");
  assert.equal(err.name, "ApiError");
});

test("shouldRetryColdStartRequest restricts auto-retry to idempotent requests and /auth/login", () => {
  assert.equal(shouldRetryColdStartRequest("/api/v1/documents", "GET"), true);
  assert.equal(shouldRetryColdStartRequest("/api/v1/health"), true);
  assert.equal(shouldRetryColdStartRequest("/api/v1/auth/login", "POST"), true);
  assert.equal(
    shouldRetryColdStartRequest("/api/v1/documents/123/generate-notes", "POST"),
    false,
  );
  assert.equal(shouldRetryColdStartRequest("/api/v1/documents/123", "DELETE"), false);
});

test("apiFetch retries transient TypeError/502 cold-start errors on GET without retrying POST mutations", async () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;

  globalThis.fetch = (async () => {
    calls += 1;
    if (calls === 1) {
      throw new TypeError("Failed to fetch");
    }
    if (calls === 2) {
      return new Response("Bad Gateway", {
        status: 502,
        headers: { "Content-Type": "text/html" },
      });
    }
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;

  try {
    const result = await apiFetch<{ ok: boolean }>(
      "/api/v1/documents",
      { method: "GET" },
      [1, 1],
    );
    assert.deepEqual(result, { ok: true });
    assert.equal(calls, 3);

    calls = 0;
    await assert.rejects(
      () =>
        apiFetch<{ ok: boolean }>(
          "/api/v1/documents",
          { method: "POST", body: JSON.stringify({}) },
          [1, 1],
        ),
      (err: unknown) => err instanceof TypeError,
    );
    assert.equal(calls, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
