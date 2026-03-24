# DOM Manipulation and Web APIs

## DOM Querying and Manipulation
```javascript
// Querying
const el = document.querySelector('.class');          // first match
const els = document.querySelectorAll('div > p');     // NodeList (static)
const live = document.getElementsByClassName('x');    // HTMLCollection (live)

// Creation and insertion
const div = document.createElement('div');
div.textContent = 'content';
div.classList.add('active');
parent.appendChild(div);                              // end
parent.insertBefore(div, reference);                  // before ref
parent.replaceChild(newEl, oldEl);
el.remove();
```

## Event Delegation (performance pattern)
```javascript
// BAD: 1000 listeners for 1000 items
items.forEach(item => item.addEventListener('click', handler));

// GOOD: 1 listener on parent
document.getElementById('list').addEventListener('click', (e) => {
  const item = e.target.closest('[data-id]');
  if (item) handle(item.dataset.id);
});
```
Use for: dynamic lists, large tables, any repeated element pattern.

## Fetch API
```javascript
const response = await fetch(url, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
  body: JSON.stringify(data),
  signal: AbortController.signal,  // cancellation
});
if (!response.ok) throw new Error(`HTTP ${response.status}`);
const json = await response.json();
```

## Web Workers (CPU-heavy tasks off main thread)
```javascript
// worker.js
self.onmessage = ({ data }) => self.postMessage(heavyComputation(data));

// main.js
const worker = new Worker('./worker.js');
worker.postMessage(inputData);
worker.onmessage = ({ data }) => console.log(data);
```
Use for: image processing, large data parsing, crypto, ML inference.

## Service Workers (PWA, offline, caching)
```javascript
// Register
navigator.serviceWorker.register('/sw.js');

// sw.js — cache-first strategy
self.addEventListener('fetch', (e) => {
  e.respondWith(caches.match(e.request).then(cached => cached ?? fetch(e.request)));
});
```
Lifecycle: install → activate → fetch. Runs in separate thread, no DOM access.

## Storage APIs
| API | Capacity | Persistence | Async | Use case |
|-----|---------|-------------|-------|---------|
| localStorage | ~5MB | Until cleared | No | User preferences, tokens |
| sessionStorage | ~5MB | Tab lifetime | No | Form state, wizard steps |
| IndexedDB | GB range | Until cleared | Yes | Offline data, large objects |
| Cache API | Varies | Until cleared | Yes | Service Worker assets |

```javascript
// IndexedDB (via idb library — recommended over raw API)
const db = await openDB('mydb', 1, {
  upgrade(db) { db.createObjectStore('items', { keyPath: 'id' }); }
});
await db.put('items', { id: 1, name: 'test' });
```

## WebSockets
```javascript
const ws = new WebSocket('wss://api.example.com/ws');
ws.onopen = () => ws.send(JSON.stringify({ type: 'subscribe', channel: 'prices' }));
ws.onmessage = ({ data }) => handle(JSON.parse(data));
ws.onerror = (e) => reconnect();
// Reconnection: exponential backoff (1s, 2s, 4s, max 30s)
```

## Intersection Observer (lazy loading, infinite scroll)
```javascript
const observer = new IntersectionObserver((entries) => {
  entries.forEach(e => { if (e.isIntersecting) loadImage(e.target); });
}, { threshold: 0.1, rootMargin: '100px' });
document.querySelectorAll('img[data-src]').forEach(img => observer.observe(img));
```

## ResizeObserver (responsive components)
```javascript
const ro = new ResizeObserver(entries => {
  for (const entry of entries) {
    const { width } = entry.contentRect;
    entry.target.classList.toggle('compact', width < 400);
  }
});
ro.observe(document.getElementById('widget'));
```
