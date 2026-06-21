export type SimpleStatus = "pending" | "ok" | "failed";

export function formatBooleanStatus(value: boolean): Exclude<SimpleStatus, "pending"> {
  return value ? "ok" : "failed";
}

export function summarizeAssetStatus({
  checked,
  failed
}: {
  checked: number;
  failed: number;
}): SimpleStatus {
  if (checked === 0) {
    return "pending";
  }
  return failed === 0 ? "ok" : "failed";
}
