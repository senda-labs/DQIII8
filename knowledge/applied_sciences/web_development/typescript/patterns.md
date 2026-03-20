# TypeScript Design Patterns

## Dependency Injection
```typescript
interface Logger { log(msg: string): void; }
interface UserRepository { findById(id: number): Promise<User>; }

class UserService {
  constructor(
    private readonly repo: UserRepository,
    private readonly logger: Logger
  ) {}
  async getUser(id: number) {
    this.logger.log(`Fetching user ${id}`);
    return this.repo.findById(id);
  }
}
// Test: inject mock implementations
```
Benefits: testable, decoupled, swappable implementations.

## Repository Pattern
```typescript
interface Repository<T, ID> {
  findById(id: ID): Promise<T | null>;
  findAll(): Promise<T[]>;
  save(entity: T): Promise<T>;
  delete(id: ID): Promise<void>;
}

class UserRepository implements Repository<User, number> {
  constructor(private readonly db: Database) {}
  async findById(id: number) { return this.db.query('SELECT * FROM users WHERE id = ?', [id]); }
  // ...
}
```

## Factory Pattern
```typescript
interface Notification { send(to: string, msg: string): Promise<void>; }

class NotificationFactory {
  static create(type: 'email' | 'sms' | 'push'): Notification {
    switch (type) {
      case 'email': return new EmailNotification();
      case 'sms': return new SMSNotification();
      case 'push': return new PushNotification();
    }
  }
}
```

## Builder Pattern
```typescript
class QueryBuilder {
  private filters: string[] = [];
  private limitVal?: number;

  where(condition: string): this { this.filters.push(condition); return this; }
  limit(n: number): this { this.limitVal = n; return this; }
  build(): string {
    let q = 'SELECT * FROM table';
    if (this.filters.length) q += ` WHERE ${this.filters.join(' AND ')}`;
    if (this.limitVal) q += ` LIMIT ${this.limitVal}`;
    return q;
  }
}
// new QueryBuilder().where('age > 18').limit(10).build()
```

## Advanced Types

### Conditional Types
```typescript
type IsArray<T> = T extends any[] ? true : false;
type Flatten<T> = T extends Array<infer Item> ? Item : T;
// Flatten<string[]> → string
// Flatten<number>   → number
```

### Mapped Types
```typescript
type Optional<T> = { [K in keyof T]?: T[K] };
type Nullable<T> = { [K in keyof T]: T[K] | null };
type Getters<T> = { [K in keyof T as `get${Capitalize<string & K>}`]: () => T[K] };
```

### `infer` Keyword
```typescript
type UnpackPromise<T> = T extends Promise<infer U> ? U : T;
type FirstArg<F> = F extends (first: infer A, ...rest: any[]) => any ? A : never;
```

## Error Handling: Result<T, E> Pattern
```typescript
type Result<T, E = Error> = { ok: true; value: T } | { ok: false; error: E };

async function parseUser(raw: unknown): Promise<Result<User, string>> {
  if (!isUser(raw)) return { ok: false, error: 'Invalid user data' };
  return { ok: true, value: raw };
}

// Usage: explicit, no try-catch needed at call site
const result = await parseUser(data);
if (!result.ok) return handleError(result.error);
processUser(result.value); // TypeScript knows value is User here
```

vs. try-catch:
- Result<T,E>: explicit error types, composable, no implicit throws, functional style
- try-catch: simpler for one-off operations, required for async boundary errors
- Recommendation: Result for domain errors, try-catch for infrastructure/IO errors
