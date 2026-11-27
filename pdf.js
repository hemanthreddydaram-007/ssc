/**
 * Browser-side PDF text extraction using PDF.js (lazy-loaded on first .pdf upload).
 * Reconstructs visual reading lines using (x, y) coordinates so PYQ questions, options,
 * and answer keys keep their line structure across columns and pages.
 */

const PDFJS_LIB_URL = "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.min.mjs";
const PDFJS_WORKER_URL = "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.worker.min.mjs";

let pdfjsPromise = null;

/**
 * Reconstructs ordered text lines from PDF.js getTextContent() items using (x, y) positions.
 */
export function reconstructLinesFromPdfItems(items) {
  if (!Array.isArray(items) || items.length === 0) return [];

  const rows = [];
  const Y_TOLERANCE = 3;

  for (const item of items) {
    if (!item || typeof item.str !== "string") continue;
    const text = item.str;
    const x = Array.isArray(item.transform) ? Number(item.transform[4]) || 0 : 0;
    const y = Array.isArray(item.transform) ? Number(item.transform[5]) || 0 : 0;
    const width = Number(item.width) || 0;

    if (!text.trim() && !item.hasEOL) continue;

    let row = rows.find((r) => Math.abs(r.y - y) <= Y_TOLERANCE);
    if (!row) {
      row = { y, chunks: [] };
      rows.push(row);
    }
    row.chunks.push({ x, width, text });
  }

  rows.sort((a, b) => b.y - a.y);

  const lines = [];
  for (const row of rows) {
    row.chunks.sort((a, b) => a.x - b.x);
    let line = "";
    let prevEndX = null;

    for (const chunk of row.chunks) {
      const piece = chunk.text;
      if (!piece) continue;
      if (line.length > 0 && prevEndX !== null) {
        const gap = chunk.x - prevEndX;
        if (gap > 0.8 && !line.endsWith(" ") && !piece.startsWith(" ")) {
          line += " ";
        }
      }
      line += piece;
      prevEndX = chunk.x + (chunk.width > 0 ? chunk.width : piece.length * 4);
    }

    const trimmed = line.replace(/\s+/g, " ").trim();
    if (trimmed) {
      lines.push(trimmed);
    }
  }

  return lines;
}

async function getPdfJs() {
  if (!pdfjsPromise) {
    pdfjsPromise = (async () => {
      const pdfjsLib = await import(PDFJS_LIB_URL);
      if (!pdfjsLib.GlobalWorkerOptions.workerSrc) {
        try {
          const workerRes = await fetch(PDFJS_WORKER_URL);
          if (workerRes.ok) {
            const workerText = await workerRes.text();
            const blobUrl = URL.createObjectURL(
              new Blob([workerText], { type: "text/javascript" })
            );
            pdfjsLib.GlobalWorkerOptions.workerSrc = blobUrl;
          } else {
            pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_WORKER_URL;
          }
        } catch {
          pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_WORKER_URL;
        }
      }
      return pdfjsLib;
    })().catch((err) => {
      pdfjsPromise = null;
      throw err;
    });
  }
  return pdfjsPromise;
}

/**
 * Extracts structured plain text from a File/Blob or ArrayBuffer of a .pdf document.
 */
export async function extractTextFromPdfFile(fileOrBuffer) {
  let pdfjsLib;
  try {
    pdfjsLib = await getPdfJs();
  } catch (err) {
    throw new Error(
      `Could not load PDF reader (${err.message}). Check internet connection or use .txt / .csv / .json.`
    );
  }

  const buffer =
    fileOrBuffer instanceof ArrayBuffer
      ? fileOrBuffer
      : await fileOrBuffer.arrayBuffer();

  const loadingTask = pdfjsLib.getDocument({ data: new Uint8Array(buffer) });
  const pdf = await loadingTask.promise;
  const pageTexts = [];

  for (let pageNum = 1; pageNum <= pdf.numPages; pageNum += 1) {
    const page = await pdf.getPage(pageNum);
    const content = await page.getTextContent();
    const lines = reconstructLinesFromPdfItems(content.items);
    if (lines.length > 0) {
      pageTexts.push(lines.join("\n"));
    }
  }

  return pageTexts.join("\n\n");
}
