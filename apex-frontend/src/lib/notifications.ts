import type { Alert } from "@/types";

let permissionRequested = false;

export async function initNotifications(): Promise<boolean> {
  if (typeof window === "undefined" || !("Notification" in window)) {
    return false;
  }
  if (Notification.permission === "granted") {
    await registerServiceWorker();
    return true;
  }
  if (Notification.permission === "denied" || permissionRequested) {
    return false;
  }
  permissionRequested = true;
  const result = await Notification.requestPermission();
  if (result === "granted") {
    await registerServiceWorker();
    return true;
  }
  return false;
}

async function registerServiceWorker(): Promise<void> {
  if (!("serviceWorker" in navigator)) return;
  try {
    await navigator.serviceWorker.register("/apex-sw.js");
  } catch {
    /* SW registration failed */
  }
}

export async function showDesktopNotification(alert: Alert): Promise<void> {
  if (typeof window === "undefined" || !("Notification" in window)) return;
  if (Notification.permission !== "granted") return;

  const requireInteraction =
    alert.fullscreen === true ||
    alert.type === "kill_switch" ||
    alert.type === "high_confidence";

  const payload = {
    title: alert.title_ar,
    body: alert.message_ar,
    tag: alert.id,
    requireInteraction,
  };

  if ("serviceWorker" in navigator) {
    const reg = await navigator.serviceWorker.ready.catch(() => null);
    if (reg?.active) {
      reg.active.postMessage({ type: "APEX_ALERT", payload });
      return;
    }
  }

  new Notification(alert.title_ar, {
    body: alert.message_ar,
    tag: alert.id,
    dir: "rtl",
    lang: "ar",
    requireInteraction,
  });
}
