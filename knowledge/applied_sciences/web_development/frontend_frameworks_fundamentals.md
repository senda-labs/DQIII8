# Frontend Frameworks Fundamentals

## Definition
Frontend frameworks are libraries and tools that provide structured approaches for building interactive user interfaces. They abstract browser APIs, manage application state, and enable component-based development, dramatically accelerating the creation of complex web applications.

## Core Concepts

- **Component-Based Architecture:** UI is broken into reusable, self-contained components that manage their own markup, style, and logic. Components accept props (inputs) and emit events (outputs). Composition over inheritance.
- **Declarative vs. Imperative:** Frameworks are declarative — describe *what* the UI should look like given state, not *how* to manipulate the DOM. The framework handles DOM updates efficiently.
- **Virtual DOM (React, Vue):** An in-memory representation of the DOM. When state changes, the framework diffs the new virtual DOM against the old one (reconciliation) and applies only the minimal required DOM changes. React Fiber is React's reconciliation algorithm.
- **Reactivity (Vue, Svelte):** Automatically tracks data dependencies and updates only affected components when data changes. Vue 3 uses Proxy-based reactivity; Svelte compiles reactivity into imperative code at build time.
- **State Management:**
  - Local state: Component-level (React useState, Vue ref/reactive).
  - Lifted state: Shared between siblings via parent.
  - Global state: App-wide (Redux, Zustand, Pinia, Vuex, Jotai).
  - Server state: Async data from APIs (React Query, SWR, TanStack Query).
- **Routing:** Client-side routing avoids full page reloads. React Router, Vue Router, Next.js App Router. Nested routes, dynamic segments, lazy loading routes.
- **React Specifics:** Hooks (useState, useEffect, useCallback, useMemo, useContext, useRef). Rules of Hooks. Strict Mode. React Server Components (RSC) for server-rendered components.
- **Build Tools:** Vite (fast HMR, ESBuild bundling), Webpack (mature, highly configurable), Turbopack. Module bundling, tree-shaking, code splitting, asset optimization.

## Framework Comparison
| | React | Vue | Svelte | Angular |
|---|---|---|---|---|
| Paradigm | Library | Progressive framework | Compiler | Full framework |
| Learning curve | Medium | Low | Low | High |
| Ecosystem | Largest | Large | Growing | Enterprise |
| Performance | Virtual DOM | Virtual DOM | No runtime | Change detection |

## Practical Applications
- **Single Page Apps (SPA):** React + React Router + Zustand/Redux.
- **Server-Side Rendering (SSR):** Next.js (React), Nuxt (Vue) for SEO and performance.
- **Static Site Generation (SSG):** Gatsby, Astro — pre-render at build time.
- **Mobile:** React Native, Ionic, Expo for cross-platform mobile with web skills.
