self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
// Намеренно ничего не кэшируем: панель показывает живое состояние, и ответ
// из вчерашнего кэша был бы тем самым враньём, от которого мы её и лечим.
