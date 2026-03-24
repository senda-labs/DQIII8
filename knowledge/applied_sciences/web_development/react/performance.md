# React Performance Optimization

## Virtual DOM Reconciliation
React compares previous and current VDOM trees (diffing algorithm):
- Different element types → unmount + remount entire subtree
- Same type → update props in place
- Lists → use `key` prop for stable identity

```tsx
// BAD: key=index causes wrong reconciliation on reorder/insert
{items.map((item, i) => <Row key={i} {...item} />)}

// GOOD: stable, unique identity
{items.map(item => <Row key={item.id} {...item} />)}
```

## Re-render Prevention

### React.memo
```tsx
const Row = React.memo(({ item }: { item: Item }) => <tr>{item.name}</tr>);
// Only re-renders if item reference changes
// Combine with useMemo on the array if parent creates new array each render
```

### useMemo — when to use
```tsx
// ✅ Use: expensive computation
const filtered = useMemo(() => items.filter(complexPredicate), [items]);

// ❌ Skip: cheap operation (React memo overhead > saved work)
const doubled = useMemo(() => count * 2, [count]); // unnecessary
```

### useCallback — when to use
```tsx
// ✅ Use: function passed as prop to memoized child
const handleDelete = useCallback((id: string) => {
  dispatch(deleteItem(id));
}, [dispatch]);

// ❌ Skip: function used only in same component
const localFn = () => compute(); // no need to memoize
```

## Code Splitting
```tsx
// Route-level splitting (most impactful)
const Dashboard = React.lazy(() => import('./pages/Dashboard'));
const Settings = React.lazy(() => import('./pages/Settings'));

<Suspense fallback={<PageLoader />}>
  <Routes>
    <Route path="/dashboard" element={<Dashboard />} />
    <Route path="/settings" element={<Settings />} />
  </Routes>
</Suspense>

// Component-level: split heavy components (charts, editors, maps)
const HeavyChart = React.lazy(() => import('./components/Chart'));
```

## Bundle Analysis
```bash
# Vite
npx vite-bundle-visualizer

# CRA / Webpack
npx source-map-explorer 'build/static/js/*.js'

# Next.js
npx @next/bundle-analyzer
```
Targets: initial JS bundle < 200KB gzipped. Identify: large dependencies, duplicate code, unused imports.

## Web Vitals Optimization in React
| Metric | React-specific cause | Fix |
|--------|---------------------|-----|
| LCP | Large component tree blocking render | SSR, streaming, code split |
| INP | Heavy event handlers, synchronous state updates | useTransition, deferred state |
| CLS | Missing image dimensions, font loading | Specify width/height, font-display: optional |

```tsx
// useTransition: mark non-urgent updates
const [isPending, startTransition] = useTransition();
const handleSearch = (q: string) => {
  setInput(q); // urgent — update input immediately
  startTransition(() => setResults(filter(q))); // non-urgent — can defer
};
```

## Rendering Strategies (Next.js)
| Strategy | When | Staleness |
|----------|------|-----------|
| SSR (Server-Side Rendering) | Personalized, real-time data | Per request |
| SSG (Static Site Generation) | Marketing, docs, blogs | Until rebuild |
| ISR (Incremental Static Regeneration) | Content that updates periodically | revalidate seconds |
| CSR (Client-Side Rendering) | Dashboards, auth-gated, real-time | Client fetch |

```tsx
// ISR in Next.js App Router
export const revalidate = 60; // seconds

// SSR
export const dynamic = 'force-dynamic';

// SSG
export const dynamic = 'force-static';
```

## Profiling
1. React DevTools Profiler: record interaction → find components with high render time
2. `why-did-you-render` library: logs unnecessary re-renders in development
3. Chrome Performance tab: identify long tasks (>50ms) on main thread
