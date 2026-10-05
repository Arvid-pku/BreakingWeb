export interface ToastMessage {
  id: string;
  title: string;
  description?: string;
  onUndo?: () => void;
}

interface ToastProps {
  messages: ToastMessage[];
  onDismiss?: (id: string) => void;
}

export function Toast({ messages, onDismiss }: ToastProps) {
  if (messages.length === 0) {
    return null;
  }

  return (
    <div className="wab-toast-stack" aria-live="polite" aria-label="Notifications">
      {messages.map((message) => (
        <section key={message.id} className="wab-toast">
          <strong>{message.title}</strong>
          {message.description ? (
            <p style={{ marginBottom: 0, color: "var(--color-text-muted)" }}>{message.description}</p>
          ) : null}
          {message.onUndo ? (
            <button
              type="button"
              className="wab-toast-undo"
              aria-label="Undo"
              onClick={() => {
                message.onUndo?.();
                onDismiss?.(message.id);
              }}
            >
              Undo
            </button>
          ) : null}
        </section>
      ))}
    </div>
  );
}
