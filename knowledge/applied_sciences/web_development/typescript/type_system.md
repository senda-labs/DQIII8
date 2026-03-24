# TypeScript Type System

## Primitives and Special Types
```typescript
// Primitives
string, number, boolean, bigint, symbol, null, undefined

// Special
any       // opt-out of type checking (avoid)
unknown   // type-safe any — must narrow before use
never     // unreachable code, exhaustive checks
void      // function returns nothing
object    // non-primitive (avoid — prefer specific types)
```

## Interface vs Type
```typescript
// Interface: extendable, declaration merging, preferred for objects
interface User { id: number; name: string; }
interface Admin extends User { role: 'admin'; }

// Type alias: unions, intersections, computed types, primitives
type ID = string | number;
type AdminUser = User & { role: 'admin' };
type EventName = `on${string}`;  // template literal
```
Rule of thumb: use `interface` for object shapes, `type` for unions/intersections/computations.

## Generics
```typescript
function first<T>(arr: T[]): T | undefined { return arr[0]; }

// Generic constraints
function getLength<T extends { length: number }>(x: T): number { return x.length; }

// Default type parameter
type ApiResponse<T = unknown> = { data: T; error: string | null; };
```

## Utility Types
```typescript
Partial<T>          // all properties optional
Required<T>         // all properties required
Readonly<T>         // all properties readonly
Pick<T, K>          // subset of keys
Omit<T, K>          // exclude keys
Record<K, V>        // { [key in K]: V }
Exclude<T, U>       // T minus U (for unions)
Extract<T, U>       // T ∩ U (for unions)
NonNullable<T>      // remove null | undefined
ReturnType<F>       // infer return type of function
Parameters<F>       // infer parameter types as tuple
Awaited<T>          // unwrap Promise<T> → T
```

## Type Guards
```typescript
// typeof guard
function process(x: string | number) {
  if (typeof x === 'string') x.toUpperCase(); // string here
}

// instanceof guard
if (error instanceof AppError) error.code;

// User-defined type guard (type predicate)
function isUser(x: unknown): x is User {
  return typeof x === 'object' && x !== null && 'id' in x;
}

// Assertion function
function assert(cond: boolean, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}
```

## Discriminated Unions
```typescript
type Shape =
  | { kind: 'circle'; radius: number }
  | { kind: 'rect'; width: number; height: number };

function area(s: Shape): number {
  switch (s.kind) {
    case 'circle': return Math.PI * s.radius ** 2;
    case 'rect': return s.width * s.height;
    // TypeScript enforces exhaustiveness if default: throw never
  }
}
```

## Template Literal Types
```typescript
type EventName = `on${Capitalize<string>}`;
type CSSProperty = `${string}-${string}`;
type Routes = `/api/${string}`;
```

## Strict Mode (tsconfig.json)
```json
{
  "compilerOptions": {
    "strict": true,           // enables all strict flags below
    "noImplicitAny": true,    // no implicit any
    "strictNullChecks": true, // null/undefined not assignable to other types
    "strictFunctionTypes": true,
    "noUncheckedIndexedAccess": true,  // arr[0] is T | undefined
    "exactOptionalPropertyTypes": true
  }
}
```

## Declaration Files (.d.ts)
```typescript
// For JS libraries without types
declare module 'legacy-lib' {
  export function doThing(x: string): number;
}
// Install types: npm install --save-dev @types/library-name
// Check availability: https://www.typescriptlang.org/dt/search
```
