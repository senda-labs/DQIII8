---
domain: applied_sciences
agent: software-specialist
keywords_es: [patrón diseño, singleton, factory, observer, SOLID, arquitectura, GoF, strategy, decorator, adapter, command, state, composite]
keywords_en: [design pattern, singleton, factory, observer, SOLID, architecture, GoF, strategy, decorator, adapter, command, state, composite]
---

# Design Patterns — Decision Matrix

## GoF 23 Patterns — When to Use / Not Use

| Pattern | Category | Use When | Do NOT Use When | Key Intent |
|---------|----------|----------|-----------------|-----------|
| Singleton | Creational | exactly 1 instance needed (config, logger, connection pool) | need testability/mocking; 1 instance is accidental | single shared instance |
| Factory Method | Creational | subclass determines which object to instantiate | only 1 concrete type; subclasses not needed | defer instantiation to subclass |
| Abstract Factory | Creational | families of related objects; platform variants | only 1 platform; single product families | related product families |
| Builder | Creational | complex object with many optional parts; telescoping constructor | object has 1-2 params; simple construction | step-by-step construction |
| Prototype | Creational | cloning expensive-to-create objects; avoid subclassing | objects are immutable; shallow copy OK | clone instead of new |
| Adapter | Structural | incompatible interface must be used | can modify original class | interface compatibility |
| Bridge | Structural | decouple abstraction from implementation; both vary independently | implementation won't change | independent variation |
| Composite | Structural | tree structures; treat leaf and composite uniformly | no tree structure; types differ significantly | tree uniform treatment |
| Decorator | Structural | add responsibilities dynamically at runtime | fixed variations known at compile time; only 1-2 variations | transparent wrapping |
| Facade | Structural | simplify complex subsystem; provide simpler interface | subsystem already simple; need full access | simplified interface |
| Flyweight | Structural | huge number of similar objects; memory critical | objects aren't similar enough to share | share fine-grained objects |
| Proxy | Structural | control access, add lazy loading, cache, logging | direct access is fine; overhead not justified | surrogate with control |
| Chain of Responsibility | Behavioral | multiple handlers may process request; order matters | only 1 handler; handler always fixed | pass request along chain |
| Command | Behavioral | encapsulate actions as objects; undo/redo; queue operations | no need for undo; simple synchronous actions | encapsulate operations |
| Interpreter | Behavioral | simple grammar to interpret; DSL needed | complex grammar; use parser generator instead | language grammar |
| Iterator | Behavioral | traverse collection without exposing internals | single traversal; collection already iterable | sequential access |
| Mediator | Behavioral | reduce many-to-many dependencies between objects | only 2-3 objects communicating | centralize communication |
| Memento | Behavioral | undo/redo; snapshot/restore state | state too large; frequent snapshots | capture/restore state |
| Observer | Behavioral | 1-to-many notification; event system | tight coupling OK; order of notification matters critically | broadcast notification |
| State | Behavioral | object behavior changes significantly based on state | few states with simple transitions | state-dependent behavior |
| Strategy | Behavioral | family of interchangeable algorithms; swap at runtime | only 1 algorithm; no variation needed | interchangeable algorithms |
| Template Method | Behavioral | define algorithm skeleton; let subclasses fill in steps | algorithm steps vary wildly across subclasses | skeleton with hooks |
| Visitor | Behavioral | add operations to class hierarchy without modifying it | class hierarchy changes frequently | separate operation from structure |

## SOLID Principles — Rules & Anti-patterns

| Principle | Rule | Correct | Anti-pattern |
|-----------|------|---------|-------------|
| **S** — Single Responsibility | 1 class = 1 reason to change | UserRepository only does DB ops | God Class (handles auth + DB + email + validation) |
| **O** — Open/Closed | Open for extension, closed for modification | Add new payment via new PaymentStrategy impl | Switch/if-else on payment type in core class |
| **L** — Liskov Substitution | Subtype must be substitutable for supertype | Square and Rectangle are separate, not Square extends Rectangle | Square extends Rectangle (setWidth breaks Square's invariants) |
| **I** — Interface Segregation | Many specific interfaces > one fat interface | IReader, IWriter, ISerializer (separate) | IAnimal with swim(), fly(), run() forced on all animals |
| **D** — Dependency Inversion | Depend on abstractions, not concretions | inject IRepository into service | new MySQLRepository() inside business logic |

## 12-Factor App Compliance

| Factor | DO | DON'T |
|--------|----|-------|
| Codebase | 1 codebase, many deploys | separate repos per environment |
| Dependencies | declare in manifest (pip, npm); isolate with venv/node_modules | system-wide package assumptions |
| Config | store in environment variables | hardcode config in code; commit .env |
| Backing services | treat DBs, queues, caches as attached resources (URL in env) | hardcode DB hostname/port |
| Build/Release/Run | strict separation of build, release, run stages | build-time code changes in production |
| Processes | stateless; share nothing; persist state in backing services | in-memory session state; local filesystem as cache |
| Port binding | export services via port binding (self-contained) | rely on webserver injection (Apache mod_) |
| Concurrency | scale out via process model | thread-based scaling; single large process |
| Disposability | fast startup (<seconds); graceful shutdown | long startup; data loss on SIGTERM |
| Dev/Prod parity | keep dev, staging, prod as similar as possible | use SQLite dev vs PostgreSQL prod |
| Logs | treat as event streams (stdout/stderr); no log file management | log to files; rotate in app code |
| Admin processes | run as one-off processes (migrations, REPL) | bake admin tasks into the running app |

## Common Pattern Combinations

```
Strategy + Factory: Factory creates the right Strategy
Observer + Mediator: Mediator acts as the event hub
Decorator + Factory: Factory creates correct Decorator chain
Command + Memento: Memento stores state for Command undo
Composite + Iterator: Iterator traverses Composite tree
Proxy + Singleton: Proxy lazily initializes Singleton
```

**Source:** Gamma, Helm, Johnson, Vlissides "Design Patterns: Elements of Reusable Object-Oriented Software" (GoF, 1994) + Martin "Clean Architecture" (2017) + 12factor.net
