// service-worker.js
// نسخة بسيطة - مطلوبة عشان الموقع يتحول لتطبيق أندرويد عن طريق PWABuilder

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // بنسيب المتصفح يتعامل مع الطلبات عادي (مفيش تخزين مؤقت معقد دلوقتي)
  event.respondWith(fetch(event.request));
});

// ===== إشعارات Push (من Firebase Cloud Messaging) =====
self.addEventListener('push', (event) => {
  let payload = {};
  try { payload = event.data ? event.data.json() : {}; } catch (e) {}
  const d = payload.data || payload.notification || payload || {};
  const title = d.title || 'Egyptian Gold';
  event.waitUntil(self.registration.showNotification(title, {
    body: d.body || '',
    icon: 'icon-192.png',
    badge: 'icon-192.png',
    tag: d.tag || 'eg-gold',
    dir: 'rtl',
    lang: 'ar',
    data: { url: d.url || './' },
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || './';
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
    for (const c of list) { if ('focus' in c) return c.focus(); }
    return self.clients.openWindow(url);
  }));
});
