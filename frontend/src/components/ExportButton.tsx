export function ExportButton({
  disabled = false,
  label = "导出 CSV",
  onClick,
  busy = false,
}: {
  disabled?: boolean;
  label?: string;
  onClick?: () => void;
  busy?: boolean;
}) {
  return (
    <button
      className="button button-secondary"
      disabled={disabled || busy}
      onClick={onClick}
      type="button"
      aria-label={label}
    >
      {busy ? "准备下载…" : label}
    </button>
  );
}
