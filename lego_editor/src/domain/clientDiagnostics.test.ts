import { describe, expect, it } from "vitest";

import {
  formatBooleanStatus,
  summarizeAssetStatus,
  webglUnavailableMessage
} from "./clientDiagnostics";

describe("client diagnostics", () => {
  it("formats boolean status for visible diagnostics", () => {
    expect(formatBooleanStatus(true)).toBe("ok");
    expect(formatBooleanStatus(false)).toBe("failed");
  });

  it("summarizes asset loading status", () => {
    expect(summarizeAssetStatus({ checked: 0, failed: 0 })).toBe("pending");
    expect(summarizeAssetStatus({ checked: 2, failed: 0 })).toBe("ok");
    expect(summarizeAssetStatus({ checked: 2, failed: 1 })).toBe("failed");
  });

  it("describes disabled WebGL without warning when WebGL is available", () => {
    expect(webglUnavailableMessage(true)).toBeNull();
    expect(webglUnavailableMessage(false)).toContain("WebGL is disabled");
  });
});
