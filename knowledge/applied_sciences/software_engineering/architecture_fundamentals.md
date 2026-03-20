# Software Architecture Fundamentals

## Definition
Software architecture is the high-level structure of a software system — the decisions about how components are organized, how they communicate, and how they fulfill quality attributes (performance, scalability, maintainability, security). Architecture decisions are costly to change later.

## Core Concepts

- **Architectural Styles:**
  - Monolith: All components in a single deployable unit. Simple to develop and deploy initially; becomes hard to scale and maintain at large scale.
  - Microservices: System decomposed into small, independently deployable services communicating over APIs. High operational complexity; enables independent scaling and deployment.
  - Event-Driven: Components communicate via events (Kafka, RabbitMQ). Decoupled; good for asynchronous workflows and audit trails.
  - Layered (N-tier): Presentation → Business Logic → Data Access → Database. Classic separation of concerns.
  - Serverless/FaaS: Functions triggered by events. Extreme operational simplicity; cold start latency, vendor lock-in trade-offs.
- **Design Principles:**
  - SOLID: Single responsibility, Open-closed, Liskov substitution, Interface segregation, Dependency inversion.
  - DRY (Don't Repeat Yourself), KISS (Keep It Simple), YAGNI (You Aren't Gonna Need It).
  - Separation of Concerns, Encapsulation, High cohesion / Low coupling.
- **Distributed Systems Challenges:** CAP theorem (Consistency, Availability, Partition tolerance — pick 2). Network partitions are inevitable, so choose between consistency and availability. BASE (Basically Available, Soft state, Eventually consistent) vs. ACID.
- **API Design:** REST (stateless, resource-based, HTTP verbs), GraphQL (query language, client-defined responses), gRPC (binary protocol, generated stubs, streaming).
- **Scalability Patterns:** Horizontal vs. vertical scaling. Caching (L1/L2/CDN, cache invalidation). Load balancing (round-robin, least connections). Database sharding, read replicas, CQRS (Command Query Responsibility Segregation).
- **Observability:** Metrics (Prometheus, Grafana), Logs (ELK, Loki), Traces (Jaeger, Zipkin). The three pillars. SLOs, SLAs, error budgets.

## Architecture Decision Records (ADRs)
Document significant architectural decisions: context → decision → consequences.

## Practical Applications
- **Cloud-native:** 12-factor app principles, Kubernetes orchestration, service mesh (Istio).
- **Data pipelines:** Lambda/Kappa architecture for stream + batch processing.
- **Security:** Zero-trust architecture, defense in depth, least privilege.
- **Startups:** Start monolith, extract services when pain is felt.
