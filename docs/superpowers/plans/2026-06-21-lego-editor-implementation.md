# LEGO Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build the first browser-based 3D LEGO task editor under `lego_editor/`.

**Architecture:** Create an isolated Vite React TypeScript app. Keep LEGO rules in pure TypeScript domain modules, then connect them to a three.js canvas and inspector UI. Export repository-compatible `settings.json` and first-pass `task.json`.

**Tech Stack:** Vite, React, TypeScript, Vitest, Three.js, `@react-three/fiber`, `@react-three/drei`.

---

### Task 1: Project Skeleton

**Files:**
- Create: `lego_editor/package.json`
- Create: `lego_editor/index.html`
- Create: `lego_editor/tsconfig.json`
- Create: `lego_editor/tsconfig.node.json`
- Create: `lego_editor/vite.config.ts`
- Create: `lego_editor/src/main.tsx`
- Create: `lego_editor/src/App.tsx`
- Create: `lego_editor/src/styles.css`

- [x] **Step 1: Add package metadata and scripts**

Create a package named `lego-editor` with scripts:

```json
{
  "scripts": {
    "dev": "vite --host 127.0.0.1",
    "build": "tsc -b && vite build",
    "test": "vitest run",
    "test:watch": "vitest"
  }
}
```

- [x] **Step 2: Add minimal React entrypoint**

Create `src/main.tsx` that renders `<App />` into `#root`.

- [x] **Step 3: Add a placeholder app shell**

Create `src/App.tsx` with left library, center scene placeholder, and right inspector placeholder.

- [x] **Step 4: Verify skeleton**

Run: `npm install` from `lego_editor/`, then `npm run build`.
Expected: TypeScript and Vite build pass.

### Task 2: Domain Model and Grid Rules

**Files:**
- Create: `lego_editor/src/domain/types.ts`
- Create: `lego_editor/src/domain/brickSpecs.ts`
- Create: `lego_editor/src/domain/grid.ts`
- Create: `lego_editor/src/domain/grid.test.ts`

- [x] **Step 1: Write failing grid tests**

Tests must cover `lego_2x4` footprints for `ori=0` and `ori=1`, baseplate bounds, and occupied stud keys.

- [x] **Step 2: Run tests to verify failure**

Run: `npm test -- grid.test.ts`.
Expected: FAIL because `footprintStuds`, `isInsideBaseplate`, and `occupancyKey` do not exist.

- [x] **Step 3: Implement grid helpers**

Implement:

```ts
footprintStuds(spec, grid): StudCoord[]
isInsideBaseplate(studs, baseplate): boolean
occupancyKey(stud): string
```

- [x] **Step 4: Run tests to verify pass**

Run: `npm test -- grid.test.ts`.
Expected: PASS.

### Task 3: Validators and Build Order

**Files:**
- Create: `lego_editor/src/domain/validators.ts`
- Create: `lego_editor/src/domain/validators.test.ts`

- [x] **Step 1: Write failing validation tests**

Tests must cover overlap blocking, unsupported stacked placement blocking, valid support, dependency extraction, and topological sorting that reorders upper-layer bricks after lower-layer bricks.

- [x] **Step 2: Run tests to verify failure**

Run: `npm test -- validators.test.ts`.
Expected: FAIL because validator functions do not exist.

- [x] **Step 3: Implement validators**

Implement:

```ts
validateCandidate(scene, candidate): ValidationResult
buildDependencyGraph(bricks): Map<string, Set<string>>
sortBuildOrder(bricks, history): BuildOrderResult
```

- [x] **Step 4: Run tests to verify pass**

Run: `npm test -- validators.test.ts`.
Expected: PASS.

### Task 4: Exporters

**Files:**
- Create: `lego_editor/src/domain/exporters.ts`
- Create: `lego_editor/src/domain/exporters.test.ts`

- [x] **Step 1: Write failing exporter tests**

Tests must verify `settings.json` contains final brick entries and `task.json` includes `press_side: null`, `press_offset: null`, and `planning.press_strategy: "unplanned"`.

- [x] **Step 2: Run tests to verify failure**

Run: `npm test -- exporters.test.ts`.
Expected: FAIL because exporter functions do not exist.

- [x] **Step 3: Implement exporters**

Implement:

```ts
exportSettings(scene): SettingsJson
exportTask(scene, buildOrder): TaskJson
downloadJson(filename, data): void
```

- [x] **Step 4: Run tests to verify pass**

Run: `npm test -- exporters.test.ts`.
Expected: PASS.

### Task 5: Editor State and UI Components

**Files:**
- Create: `lego_editor/src/state/editorStore.ts`
- Create: `lego_editor/src/components/BrickLibrary.tsx`
- Create: `lego_editor/src/components/Inspector.tsx`
- Modify: `lego_editor/src/App.tsx`
- Modify: `lego_editor/src/styles.css`

- [x] **Step 1: Add store actions**

Implement state for selected type, color, rotation, scene bricks, placement history, validation messages, selected brick, and export warnings.

- [x] **Step 2: Add left library**

Render brick type buttons, color swatches, and rotation controls.

- [x] **Step 3: Add right inspector**

Render selected brick details, legality status, placement order, press strategy fields, and export buttons.

- [x] **Step 4: Run build**

Run: `npm run build`.
Expected: PASS.

### Task 6: 3D Scene

**Files:**
- Create: `lego_editor/src/components/LegoScene.tsx`
- Modify: `lego_editor/src/App.tsx`
- Modify: `lego_editor/src/styles.css`

- [x] **Step 1: Add baseplate and brick rendering**

Render a studded baseplate and programmatic LEGO bricks using cuboids and cylinders.

- [x] **Step 2: Add click placement**

Clicking a top surface proposes a snapped candidate and calls the store placement action.

- [x] **Step 3: Add hover ghost and invalid highlight**

Show a translucent candidate brick and validation state before placement.

- [x] **Step 4: Run build**

Run: `npm run build`.
Expected: PASS.

### Task 7: Final Verification

**Files:**
- No new files.

- [x] **Step 1: Run all tests**

Run: `npm test`.
Expected: PASS.

- [x] **Step 2: Run production build**

Run: `npm run build`.
Expected: PASS.

- [x] **Step 3: Start local dev server**

Run: `npm run dev -- --port 5174`.
Expected: Vite reports a local URL.

- [x] **Step 4: Verify browser render**

Open the local URL and confirm the app loads, panels render, and the canvas is nonblank.
