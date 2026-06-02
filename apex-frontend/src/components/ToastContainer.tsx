"use client";

import type { Alert } from "@/types";

interface Props {
  toasts: Alert[];
}

export default function ToastContainer({ toasts }: Props) {
  if (toasts.length === 0) return null;

  return (
    <div className="toast-container">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`toast ${toast.type === "high_confidence" ? "toast-high-confidence" : ""}`}
        >
          <strong>{toast.title_ar}</strong>
          <span>{toast.message_ar}</span>
        </div>
      ))}
    </div>
  );
}
