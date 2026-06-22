import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import { exportSettings, exportTask } from "../src/domain/exporters";
import { createSampleScene, type SampleDifficulty } from "../src/domain/sampleScenes";
import { sortBuildOrder } from "../src/domain/validators";

const difficulties: SampleDifficulty[] = ["easy", "middle", "hard"];
const outputRoot = path.resolve(process.argv[2] ?? "../config/lego_editor_samples");

function writeJson(filePath: string, data: unknown) {
  writeFileSync(filePath, `${JSON.stringify(data, null, 2)}\n`);
}

for (const difficulty of difficulties) {
  const scene = createSampleScene(difficulty);
  const order = sortBuildOrder(scene);
  if (!order.ok) {
    throw new Error(`Sample ${difficulty} has invalid build order: ${order.errors.join("; ")}`);
  }

  const configDir = path.join(outputRoot, difficulty);
  mkdirSync(configDir, { recursive: true });
  writeJson(path.join(configDir, "settings.json"), exportSettings(scene));
  writeJson(path.join(configDir, "task.json"), exportTask(scene, order.brickIds));
}

console.log(`wrote ${difficulties.length} sample config dirs to ${outputRoot}`);
