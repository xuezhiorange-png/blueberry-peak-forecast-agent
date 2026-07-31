export function ExportButton({
  disabled = true,
  label = "导出 CSV",
}: {
  disabled?: boolean;
  label?: string;
}) {
  return (
    <button
      className="button button-secondary"
      disabled={disabled}
      aria-describedby="export-unavailable"
    >
      {label}
    </button>
  );
}
