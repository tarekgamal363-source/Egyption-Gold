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
