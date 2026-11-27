import assert from "node:assert/strict";
import test from "node:test";

import { ApiError, extractErrorMessage } from "../lib/api/client";

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
