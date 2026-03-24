# JavaScript Core Patterns

## Event Loop
```
Call Stack → Microtask Queue → Macrotask Queue
```
- **Call Stack**: synchronous execution, LIFO
- **Microtask Queue**: Promises (.then/.catch), queueMicrotask(), MutationObserver — runs after each task, before next macrotask
- **Macrotask Queue**: setTimeout, setInterval, setImmediate, I/O callbacks — one per loop tick
- Rule: microtasks drain completely before the next macrotask runs

```javascript
console.log('1');                    // sync
setTimeout(() => console.log('4')); // macrotask
Promise.resolve().then(() => console.log('3')); // microtask
console.log('2');                    // sync
// Output: 1, 2, 3, 4
```

## Closures
Function that retains access to its lexical scope after outer function returns.
```javascript
function counter() {
  let count = 0;
  return { increment: () => ++count, get: () => count };
}
```
Use for: data encapsulation, memoization, partial application.

## Prototypal Inheritance
```javascript
// ES6 class syntax (prototype under the hood)
class Animal { speak() { return 'sound'; } }
class Dog extends Animal { speak() { return 'woof'; } }
// Object.getPrototypeOf(Dog.prototype) === Animal.prototype → true
```

## Async/Await & Promises
```javascript
// Promise chain
fetch(url).then(r => r.json()).then(data => process(data)).catch(err => handle(err));

// Async/await (syntactic sugar)
async function load() {
  try {
    const r = await fetch(url);
    return await r.json();
  } catch (err) { handle(err); }
}

// Parallel execution
const [a, b] = await Promise.all([fetchA(), fetchB()]);

// First success
const result = await Promise.any([fetch1(), fetch2()]);
```

## Destructuring & Spread
```javascript
const { a, b: renamed, c = 'default' } = obj;
const [first, , third, ...rest] = arr;
const merged = { ...obj1, ...obj2, override: 'val' };
const copy = [...arr, newItem];
```

## Modules (ESM vs CJS)
| Feature | ESM (`import/export`) | CJS (`require`) |
|---------|-----------------------|-----------------|
| Parsing | Static (tree-shakeable) | Dynamic |
| Top-level await | Yes | No |
| Browser native | Yes | No (bundler needed) |
| Node.js | `.mjs` or `"type":"module"` | Default |
| Circular deps | Live bindings | Cached snapshot |

## Error Handling Patterns
```javascript
// Custom error classes
class AppError extends Error {
  constructor(message, public code: string) { super(message); this.name = 'AppError'; }
}

// Never silently swallow
try { riskyOp(); } catch (e) {
  if (e instanceof AppError) handle(e);
  else throw e; // re-throw unknowns
}
```

## Map/Set vs Object/Array Performance
| Use case | Prefer | Reason |
|----------|--------|--------|
| Key-value, any key type | Map | O(1) get/set, iterable, preserves insertion order |
| Key-value, string keys | Object | JSON-serializable, simpler syntax |
| Unique values | Set | O(1) has(), deduplication |
| Unique objects | Set | Object equality by reference |
| Ordered with index | Array | Index access O(1), sort, map/filter |

Map vs Object lookup: comparable for small sizes; Map wins at 1000+ entries with non-string keys.
