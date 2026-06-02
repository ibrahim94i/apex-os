/* APEX OS — service worker for Windows/desktop notifications when tab is in background */

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("message", (event) => {
  const data = event.data;
  if (!data || data.type !== "APEX_ALERT") return;
  const { title, body, tag } = data.payload || {};
  if (!title) return;
  event.waitUntil(
    self.registration.showNotification(title, {
      body: body || "",
      tag: tag || "apex-alert",
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      dir: "rtl",
      lang: "ar",
      requireInteraction: data.payload?.requireInteraction === true,
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      if (clients.length > 0) {
        return clients[0].focus();
      }
      return self.clients.openWindow("/");
    })
  );
});
