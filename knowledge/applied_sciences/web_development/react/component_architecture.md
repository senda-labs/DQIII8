# React Component Architecture

## Functional Components (standard since React 16.8)
```tsx
const Button = ({ onClick, children, disabled = false }: ButtonProps) => (
  <button onClick={onClick} disabled={disabled}>{children}</button>
);
```

## Core Hooks

### useState / useReducer
```tsx
const [count, setCount] = useState(0);
// Functional update (safe for async)
setCount(prev => prev + 1);

// useReducer for complex state
const [state, dispatch] = useReducer(reducer, initialState);
```
Rule: `useReducer` when next state depends on previous state + multiple sub-values.

### useEffect
```tsx
useEffect(() => {
  const sub = subscribe(id);
  return () => sub.unsubscribe(); // cleanup
}, [id]); // dependency array — runs when id changes
```
- `[]`: run once on mount
- `[dep]`: run on dep change
- No array: run after every render (rarely needed)

### useMemo / useCallback
```tsx
const sorted = useMemo(() => [...items].sort(compareFn), [items]);
const handleClick = useCallback((id: number) => dispatch({ type: 'select', id }), [dispatch]);
```
**Do not over-memoize** — profiler first. Useful when:
- `useMemo`: expensive computation, referential stability for deps
- `useCallback`: function passed to memoized child component

### useRef
```tsx
const inputRef = useRef<HTMLInputElement>(null);
// DOM access
inputRef.current?.focus();
// Mutable value without re-render
const timerRef = useRef<ReturnType<typeof setInterval>>();
```

### useContext
```tsx
const ThemeContext = createContext<Theme>('light');
// Provider
<ThemeContext.Provider value={theme}><App /></ThemeContext.Provider>
// Consumer
const theme = useContext(ThemeContext);
```

## Custom Hooks
```tsx
function useLocalStorage<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    const stored = localStorage.getItem(key);
    return stored ? JSON.parse(stored) : initial;
  });
  const set = useCallback((v: T) => {
    setValue(v);
    localStorage.setItem(key, JSON.stringify(v));
  }, [key]);
  return [value, set] as const;
}
```

## Composition Patterns
| Pattern | When to use | Drawback |
|---------|------------|---------|
| Props | Simple data flow | Prop drilling at depth |
| Render props | Share behavior, inject UI | Nesting verbosity |
| HOC (Higher-Order Components) | Cross-cutting concerns, class era | Wrapper hell, harder to type |
| **Custom hooks** | Share stateful logic (preferred) | None (React team recommendation) |
| Context | Global state, theme, auth | Re-render on any change |

## Performance Components
```tsx
// React.memo — skip re-render if props unchanged
const ExpensiveList = React.memo(({ items }: { items: Item[] }) => (
  <ul>{items.map(i => <li key={i.id}>{i.name}</li>)}</ul>
));

// Lazy loading
const Chart = React.lazy(() => import('./Chart'));
// Suspense boundary
<Suspense fallback={<Spinner />}><Chart /></Suspense>

// Error Boundary (class-based, wraps thrown errors)
class ErrorBoundary extends Component {
  state = { error: null };
  static getDerivedStateFromError(error) { return { error }; }
  render() { return this.state.error ? <Fallback /> : this.props.children; }
}
```
