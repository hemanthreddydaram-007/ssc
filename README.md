# SSC CHSL 35s Question Drill

A lightweight static web app built with Vanilla HTML, CSS, and ES Modules for SSC CHSL Tier 1 question practice with a single strict **35 seconds per question** timer (`+2.00` right / `−0.50` wrong).

## Features

- **35s Per-Question Time Limit**: Every question gets a cumulative 35-second countdown. When 35 seconds expire, any selected option is auto-saved and the drill automatically skips to the next question (and submits when the final question finishes).
- **150 Built-In PYQs Across All 4 Tier 1 Sections**:
  - **Quantitative Aptitude**: `Set 1` (25 PYQs) & `Set 2` (25 PYQs)
  - **General Intelligence & Reasoning**: `Set 1` (25 PYQs) & `Set 2` (25 PYQs)
  - **English Comprehension**: `Set 1` (25 PYQs)
  - **General Awareness**: `Set 1` (25 PYQs)
- **Unlimited Multi-Format PYQ Importer**: Import any number of `.json`, `.csv`, or `.txt` previous-year question papers (single or multi-file upload, multi-paper JSON, drag-and-drop, sample downloads, and IndexedDB persistence without a 20-set or 100-question cap).
- **Generate Questions on Imported PYQs**:
  - **Offline Variants**: Generates fresh Quant & Reasoning practice questions with new numbers and patterns modeled on your selected PYQs.
  - **Mix & Filter PYQs**: Builds randomized drills across selected papers, sections, and topics.
  - **AI Generator (Optional Gemini API Key)**: Generates brand-new questions across all sections conditioned on your imported PYQs.
- **Results & Question Inspector**: Summarizes net score, accuracy, and Correct / Wrong / Skipped breakdowns with click-to-inspect answers and one-click **Retry Wrong & Skipped** practice.

## Local Development & Tests

Run unit tests (Node 22+):

```bash
node --test tests/engine.test.mjs
```

Serve locally for browser use:

```bash
python -m http.server 4173
```

Open `http://localhost:4173` in your browser, or deploy directly to GitHub Pages from the repository root.
