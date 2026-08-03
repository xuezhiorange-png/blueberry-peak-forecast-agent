export function displayValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

export function displayDate(value: string | null | undefined): string {
  return value ? value : "—";
}

export function formatDecimal(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return value;
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "—";
  return value.replace("T", " ").replace(/([+-]\d{2}:\d{2}|Z)$/, "");
}

export function formatReasons(values: readonly string[] | null | undefined): string {
  if (!values || values.length === 0) return "—";
  return [...values].sort().join(" · ");
}

export function formatHash(value: string | null | undefined): string {
  if (!value) return "—";
  return value;
}

export function displayFileSize(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}
