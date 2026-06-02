"use client";

import { useEffect } from "react";
import { initNotifications } from "@/lib/notifications";

export default function NotificationInitializer() {
  useEffect(() => {
    const timer = setTimeout(() => {
      initNotifications().catch(() => null);
    }, 1500);
    return () => clearTimeout(timer);
  }, []);
  return null;
}
