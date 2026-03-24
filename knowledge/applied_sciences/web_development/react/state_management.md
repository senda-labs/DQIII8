# React State Management

## Decision Framework (by complexity)
```
Local useState → Context API → Zustand/Jotai → Redux Toolkit
     ↑                ↑              ↑                ↑
  Component      Small app      Mid-size app    Large/complex app
  state only     shared state   global state    enterprise scale
```
Server state (API data) is separate: always use TanStack Query or RTK Query.

## Local State (useState / useReducer)
Best for: UI state, form fields, toggle flags, component-scoped data.
Never put in global store: scroll position, hover state, modal open/closed.

## Context API
```tsx
// Good for: theme, locale, auth user, feature flags (read-heavy, low-frequency updates)
const AuthContext = createContext<AuthState | null>(null);
export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be inside AuthProvider');
  return ctx;
};
```
**Limitation**: every consumer re-renders on any context value change.
Mitigation: split contexts by update frequency; use `useMemo` on context value.

## Zustand (lightweight, recommended for most apps)
```tsx
import { create } from 'zustand';

interface CartStore {
  items: CartItem[];
  add: (item: CartItem) => void;
  remove: (id: string) => void;
  total: () => number;
}

const useCartStore = create<CartStore>((set, get) => ({
  items: [],
  add: (item) => set(state => ({ items: [...state.items, item] })),
  remove: (id) => set(state => ({ items: state.items.filter(i => i.id !== id) })),
  total: () => get().items.reduce((sum, i) => sum + i.price, 0),
}));
```
Advantages: no boilerplate, selector-based subscriptions (no unnecessary re-renders), devtools, persist middleware.

## Jotai (atomic state)
```tsx
import { atom, useAtom } from 'jotai';
const countAtom = atom(0);
const doubleAtom = atom((get) => get(countAtom) * 2); // derived atom
function Counter() { const [count, setCount] = useAtom(countAtom); }
```
Best for: fine-grained subscriptions, derived/computed state, React Suspense integration.

## Redux Toolkit (RTK) — for large applications
```tsx
// Slice
const counterSlice = createSlice({
  name: 'counter',
  initialState: { value: 0 },
  reducers: {
    increment: state => { state.value += 1; },  // Immer under the hood
    incrementBy: (state, action: PayloadAction<number>) => { state.value += action.payload; }
  }
});
export const { increment, incrementBy } = counterSlice.actions;

// Thunk for async
export const fetchUser = createAsyncThunk('users/fetch', async (id: number) =>
  (await fetch(`/api/users/${id}`)).json()
);
```

## RTK Query (server state in Redux)
```tsx
const api = createApi({
  reducerPath: 'api',
  baseQuery: fetchBaseQuery({ baseUrl: '/api' }),
  endpoints: (build) => ({
    getUser: build.query<User, number>({ query: (id) => `users/${id}` }),
    updateUser: build.mutation<User, Partial<User>>({ query: (body) => ({ url: 'users', method: 'PUT', body }) }),
  }),
});
export const { useGetUserQuery, useUpdateUserMutation } = api;
```

## TanStack Query (React Query) — preferred for non-Redux apps
```tsx
const { data, isLoading, error } = useQuery({
  queryKey: ['user', id],
  queryFn: () => fetch(`/api/users/${id}`).then(r => r.json()),
  staleTime: 5 * 60 * 1000,   // 5 min before refetch
  gcTime: 10 * 60 * 1000,     // 10 min cache retention (formerly cacheTime)
});

const mutation = useMutation({
  mutationFn: (data: UserUpdate) => api.updateUser(data),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['user', id] }),
});
```
Features: automatic caching, background refetch, stale-while-revalidate, optimistic updates, pagination, infinite scroll.
