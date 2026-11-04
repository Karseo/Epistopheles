/* Service Worker: haelt nur die App-Dateien (Huelle) offline bereit. daten.json, buecher/ und
   korrektur/ laufen unveraendert ans Netz; die App legt sie selbst in IndexedDB ab.
   Bei jeder Aenderung an den App-Dateien VERSION erhoehen (bundle.py setzt sie beim Export). */
const VERSION = "epistopheles-v2";
const HUELLE = ["./", "index.html", "korrektur.html", "speedreader.js", "lesetext.js", "epub.js",
  "redaktion.js", "verdacht.js", "fussnoten.js", "ursache.js", "chunkansicht.js",
  "verbindungen.js", "graphlayout.js", "graphansicht.js", "manifest.webmanifest", "icon-192.png", "icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(HUELLE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((ks) => Promise.all(ks.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const r = e.request;
  if (r.method !== "GET") return;
  const url = new URL(r.url);
  if (url.origin !== location.origin) return;
  const name = url.pathname.slice(url.pathname.lastIndexOf("/") + 1) || "./";
  if (!HUELLE.includes(name) && !(r.mode === "navigate")) return;          // Daten: direkt ans Netz
  // Huelle: erst Netz (neue Version), bei Ausfall die Kopie
  e.respondWith(fetch(r).then((resp) => {
    if (resp.ok && HUELLE.includes(name)) { const kopie = resp.clone(); caches.open(VERSION).then((c) => c.put(r, kopie)); }
    return resp;
  }).catch(() => caches.match(r, { ignoreSearch: true }).then((m) => m || caches.match("index.html"))));
});
