# Design Patterns

## Definition
Design patterns are reusable solutions to commonly occurring problems in software design. Codified by the "Gang of Four" (GoF), they are organized into three categories: creational (object creation), structural (object composition), and behavioral (object interaction). Patterns are language-agnostic templates, not copy-paste code.

## Core Concepts

### Creational Patterns
- **Singleton:** Ensures only one instance of a class exists. Use for shared resources (config, thread pool, logger). Risks: global state, testing difficulty.
- **Factory Method:** Defines an interface for creating objects but lets subclasses decide which class to instantiate. Decouples client from concrete classes.
- **Abstract Factory:** Creates families of related objects without specifying concrete classes. Use when system must be independent of how its products are created.
- **Builder:** Constructs complex objects step by step. Separates construction from representation. Use for objects with many optional parameters (fluent builder pattern).
- **Prototype:** Creates new objects by cloning an existing instance. Use when object creation is expensive and a similar object already exists.

### Structural Patterns
- **Adapter:** Converts one interface into another expected by the client. Wraps an incompatible class to make it compatible. "Wrapper" pattern.
- **Decorator:** Adds responsibilities to objects dynamically without subclassing. Wraps an object and adds behavior. Python `@decorator` is a language-level version.
- **Facade:** Provides a simplified interface to a complex subsystem. Reduces dependencies; hides internal complexity.
- **Proxy:** Controls access to another object (lazy loading, caching, access control, logging). Same interface as the real object.
- **Composite:** Composes objects into tree structures to represent part-whole hierarchies. Treats individual objects and compositions uniformly. Used in UI component trees, file systems.

### Behavioral Patterns
- **Observer:** Defines a one-to-many dependency. When one object changes state, all dependents are notified. Foundation of event systems and reactive frameworks (Redux, RxJS).
- **Strategy:** Defines a family of algorithms, encapsulates each one, and makes them interchangeable. Eliminates conditional branching (replace `if/switch` with polymorphism).
- **Command:** Encapsulates a request as an object. Supports undo/redo, queuing, logging. Used in GUI actions, transaction systems.
- **Iterator:** Provides a way to access elements of a collection sequentially without exposing its internal structure.
- **Template Method:** Defines the skeleton of an algorithm in a base class, deferring some steps to subclasses. Inversion of control — framework calls your code.
- **Chain of Responsibility:** Passes a request along a chain of handlers. Each handler decides to handle or pass it on. Used in middleware pipelines (Express.js, Django).

## SOLID Principles (Structural Foundation)
- **S** — Single Responsibility: One reason to change per class/module.
- **O** — Open/Closed: Open for extension, closed for modification.
- **L** — Liskov Substitution: Subtypes must be substitutable for their base types.
- **I** — Interface Segregation: Clients should not depend on interfaces they don't use.
- **D** — Dependency Inversion: Depend on abstractions, not concretions.

## Key Distinctions
- **Composition over inheritance:** Favor combining objects over deep inheritance chains. More flexible, avoids fragile base class problem.
- **Program to interfaces:** Depend on abstractions rather than concrete implementations.
- **GoF vs. modern patterns:** Modern additions include Repository, CQRS, Event Sourcing, Saga (for distributed systems).

## Application Rules
- Use **Strategy** when you have multiple algorithms for the same task and want to switch at runtime.
- Use **Observer** when state changes in one object need to trigger updates elsewhere.
- Use **Facade** when onboarding new team members to a complex subsystem.
- Use **Decorator** when you need to add cross-cutting concerns (logging, auth, caching) without modifying classes.
