import { useEffect, useState } from "react";

interface ToastProps {
  message: string;
  action?: { label: string; onClick: () => void };
  type?: "info" | "success" | "error";
  duration?: number;
  onDismiss: () => void;
}

export function Toast({ message, action, type = "info", duration = 8000, onDismiss }: ToastProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // Trigger animation
    const showTimer = setTimeout(() => setVisible(true), 10);

    // Auto-dismiss
    const dismissTimer = setTimeout(() => {
      setVisible(false);
      setTimeout(onDismiss, 300); // Wait for animation
    }, duration);

    return () => {
      clearTimeout(showTimer);
      clearTimeout(dismissTimer);
    };
  }, [duration, onDismiss]);

  function handleDismiss() {
    setVisible(false);
    setTimeout(onDismiss, 300);
  }

  function handleAction() {
    if (action) {
      action.onClick();
      handleDismiss();
    }
  }

  return (
    <div className={`toast toast-${type} ${visible ? "toast-visible" : ""}`}>
      <span className="toast-message">{message}</span>
      <div className="toast-actions">
        {action && (
          <button type="button" className="btn btn-primary btn-xs" onClick={handleAction}>
            {action.label}
          </button>
        )}
        <button type="button" className="btn btn-secondary btn-xs" onClick={handleDismiss}>
          Dismiss
        </button>
      </div>
    </div>
  );
}
