export function ErrorState({ title = "操作未完成", message }: { title?: string; message: string }) {
  return (
    <div className="notice" role="alert">
      <span className="notice-icon" aria-hidden="true">
        !
      </span>
      <div>
        <strong>{title}</strong>
        {message}
      </div>
    </div>
  );
}
