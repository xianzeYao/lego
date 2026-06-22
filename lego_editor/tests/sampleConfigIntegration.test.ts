import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

import { describe, expect, it } from "vitest";

import { exportSettings, exportTask } from "../src/domain/exporters";
import { createSampleScene, type SampleDifficulty } from "../src/domain/sampleScenes";
import { sortBuildOrder } from "../src/domain/validators";

const difficulties: SampleDifficulty[] = ["easy", "middle", "hard"];

function writeJson(filePath: string, data: unknown) {
  writeFileSync(filePath, `${JSON.stringify(data, null, 2)}\n`);
}

describe("sample config integration", () => {
  it("writes parser-compatible settings/task pairs for all sample difficulties", () => {
    const outputRoot = mkdtempSync(path.join(tmpdir(), "lego-editor-samples-"));

    for (const difficulty of difficulties) {
      const scene = createSampleScene(difficulty);
      const order = sortBuildOrder(scene);
      expect(order.ok).toBe(true);

      const configDir = path.join(outputRoot, difficulty);
      mkdirSync(configDir, { recursive: true });
      writeJson(path.join(configDir, "settings.json"), exportSettings(scene));
      writeJson(path.join(configDir, "task.json"), exportTask(scene, order.brickIds));
    }

    const repoRoot = path.resolve(process.cwd(), "..");
    const parser = [
      "from pathlib import Path",
      "from maniskill_rm75_lego.lego_task_parser import load_task_config_dir",
      `root = Path(${JSON.stringify(outputRoot)})`,
      "for path in sorted(root.iterdir()):",
      "    task = load_task_config_dir(path)",
      "    assert len(task.bricks) == len(task.operations), path",
      "    assert all(op.pick.grid is not None for op in task.operations), path",
      "    assert all(op.pick.press_side is not None for op in task.operations), path",
      "    assert all(op.pick.press_offset is not None for op in task.operations), path",
      "print('parsed', len(list(root.iterdir())), 'sample configs')"
    ].join("\n");

    const result = spawnSync("python3", ["-c", parser], {
      cwd: repoRoot,
      encoding: "utf8",
      env: {
        ...process.env,
        PYTHONPATH: [repoRoot, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter)
      }
    });

    if (result.error && "code" in result.error && result.error.code === "EPERM") {
      console.warn("Skipping Python parser integration check: spawn blocked by sandbox.");
      return;
    }

    expect(result.error).toBeUndefined();
    expect(result.stderr).toBe("");
    expect(result.status).toBe(0);
    expect(result.stdout).toContain("parsed 3 sample configs");
  });
});
