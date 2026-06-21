import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";

function editorStateApi(): Plugin {
  let sharedState = {
    revision: 0,
    scene: null as unknown
  };

  return {
    name: "lego-editor-state-api",
    configureServer(server) {
      server.middlewares.use("/api/editor-state", (req, res) => {
        res.setHeader("Cache-Control", "no-store");
        const request = req as {
          method?: string;
          on(event: "data", callback: (chunk: unknown) => void): void;
          on(event: "end", callback: () => void): void;
        };

        if (request.method === "GET") {
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify(sharedState));
          return;
        }

        if (request.method === "POST") {
          let body = "";
          request.on("data", (chunk) => {
            body += String(chunk);
          });
          request.on("end", () => {
            try {
              const parsed = JSON.parse(body);
              sharedState = {
                revision: Number(parsed.revision) || sharedState.revision + 1,
                scene: parsed.scene
              };
              res.setHeader("Content-Type", "application/json");
              res.end(JSON.stringify(sharedState));
            } catch (error) {
              res.statusCode = 400;
              res.end(JSON.stringify({ error: "Invalid editor state payload" }));
            }
          });
          return;
        }

        res.statusCode = 405;
        res.end();
      });
    }
  };
}

export default defineConfig({
  plugins: [react(), editorStateApi()],
  server: {
    headers: {
      "Cache-Control": "no-store"
    }
  },
  test: {
    environment: "node",
    globals: true
  }
});
