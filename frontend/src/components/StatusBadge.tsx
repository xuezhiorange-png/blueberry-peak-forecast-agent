type Tone = "neutral" | "warning" | "success" | "danger";

export function StatusBadge({ label, tone = "neutral" }: { label: string; tone?: Tone }) {
  return (
    <span className="status-badge" data-tone={tone} role="status">
      {label}
    </span>
  );
}
