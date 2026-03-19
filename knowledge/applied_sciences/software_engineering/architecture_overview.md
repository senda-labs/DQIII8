# Software Architecture — Overview
**Domain:** Applied Sciences / Software Engineering
**Tier:** FREE — included in community edition

## SOLID Principles

Five design principles for object-oriented software that promote maintainability.

**S — Single Responsibility Principle**
A class or module should have one, and only one, reason to change.
If a component does two things, it should be two components.

**O — Open/Closed Principle**
Software entities should be open for extension but closed for modification.
Add new behavior by adding new code, not by changing existing code.

**L — Liskov Substitution Principle**
Objects of a subclass should be substitutable for their parent class without
breaking the program. A square is not always a safe substitute for a rectangle.

**I — Interface Segregation Principle**
Clients should not depend on interfaces they do not use.
Prefer many small, specific interfaces over one large general-purpose one.

**D — Dependency Inversion Principle**
High-level modules should not depend on low-level modules — both should depend
on abstractions. Inject dependencies; don't instantiate them internally.

## Microservices vs Monolith

### When to use a Monolith
- Early-stage product with unclear domain boundaries
- Small team (fewer than 10 engineers)
- Low traffic, single deployment target
- Speed of development is the top priority

### When to use Microservices
- Clear domain boundaries that evolve independently
- Multiple teams owning different parts of the system
- Scaling requirements differ significantly per service
- High availability requirements (isolate failures)

**Default advice:** Start with a monolith. Extract services when you feel the pain.
Premature decomposition creates distributed monolith problems.

## Common Architectural Patterns

**Repository Pattern** — Abstracts data access behind a consistent interface.
Decouples business logic from storage details.

**Event-Driven** — Components communicate via events, not direct calls.
Reduces coupling; increases observability complexity.

**CQRS** (Command Query Responsibility Segregation) — Separate read and write models.
Useful when read and write workloads have very different scaling needs.

**Hexagonal / Ports and Adapters** — Core business logic isolated from infrastructure.
External systems (DB, HTTP, queues) connect via adapters. Enables testing without
external dependencies.

**Layered (N-tier)** — Presentation → Application → Domain → Infrastructure.
Most common pattern; easy to understand; can create tight coupling if not disciplined.

## Key Heuristics

- Optimize for replaceability, not reusability
- Boring technology beats clever technology in production
- The best architecture is the one you can change tomorrow
- Complexity is a cost; add it only when the benefit is clear
