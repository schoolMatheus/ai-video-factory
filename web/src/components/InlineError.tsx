export function InlineError({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div role="alert" className="inline-error">
      <p>{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry}>
          Tentar novamente
        </button>
      )}
    </div>
  );
}
