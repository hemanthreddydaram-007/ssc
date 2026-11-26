# SSC CHSL Time Trainer

A zero-bloat static web app built with Vanilla HTML, CSS, and ES Modules to train SSC CHSL Tier 1 sectional time management (25 questions in 15:00 · 36s/question target · `+2.00` right / `−0.50` wrong).

## Features

- **150 Built-In PYQs Across All 4 Tier 1 Sections**:
  - **Quantitative Aptitude**: `Set 1` (25 PYQs) & `Set 2` (25 PYQs)
  - **General Intelligence & Reasoning**: `Set 1` (25 PYQs) & `Set 2` (25 PYQs)
  - **English Comprehension**: `Set 1` (25 PYQs)
  - **General Awareness**: `Set 1` (25 PYQs)
- **Question Shuffling & File Explorer Importer**: Optional question-order shuffling plus direct File Explorer `.json` / `.csv` import (multi-file browse, drag-and-drop, sample template downloads, schema validation, and `localStorage` persistence).

- **Mode 1 — Pure 15-Min Exam Mode**: Auto-enters fullscreen, displays a single distraction-free `15:00` master clock (no per-question timer, pace bar, or warning colors), mouse-only exam flow (`Select Option → Save & Next`, `Clear`, `Skip` + `1–25` palette), and silent `performance.now()` telemetry across revisits.
- **Mode 2 — 7-Second "Commit or Skip" Gate**: Blurs and locks options for 7 seconds on question load with `Solve Now` and `Skip` to build the `Scan → Judge → Act` habit.
- **Post-Test Step 1 — Blind Time Calibration**: Displays your slowest question before revealing scores and compares your perceived time (`Under 30s` / `30s–60s` / `Over 60s`) against exact millisecond reality.
- **Post-Test Step 2 — 4-Quadrant Time-Leak Autopsy**: Classifies every question at the 36s boundary (`Fast & Right`, `Slow & Right`, `Fast & Wrong`, `Slow & Wrong` with opportunity cost = `totalSlowWrongSec / 36`), highlights Final-Minute Panic errors (wrong answers submitted in the last 60s), offers click-to-inspect details, and provides a one-click **Retry Wrong & Slow (>36s)** loop.
- **Adaptive Overspeed Timer (v2)**: Optional toggle reading the last 2 full exam runs for a section from `localStorage` to scale between `17:00` (`<60%`), `15:00` (`60–80%`), and `13:30` (`>80%` at `≤15:00`).

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
