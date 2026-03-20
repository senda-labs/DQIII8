# Database Fundamentals

## Definition
A database is an organized collection of structured data stored and accessed electronically. Database systems (DBMS) provide mechanisms for data storage, retrieval, modification, and integrity enforcement. Choosing the right database type and design is critical for application performance and maintainability.

## Core Concepts

- **Relational Databases (SQL):** Store data in tables with rows and columns. ACID properties (Atomicity, Consistency, Isolation, Durability) guarantee transaction integrity. SQL (Structured Query Language) for querying. Examples: PostgreSQL, MySQL, SQLite, Oracle, SQL Server.
- **Normalization:** Organize tables to reduce redundancy and improve integrity. Normal forms (1NF, 2NF, 3NF, BCNF). Denormalization trades integrity for read performance.
- **Indexes:** Data structures that speed up queries by providing faster lookup paths. B-tree (range queries), hash (equality), GiST (spatial). Trade-off: faster reads, slower writes.
- **SQL Operations:** SELECT (projection, filtering), JOIN (inner, left, right, full, cross), GROUP BY + aggregates (COUNT, SUM, AVG), subqueries, window functions (ROW_NUMBER, RANK, LAG, LEAD).
- **Transactions:** Unit of work treated as atomic. ACID: all changes commit together or all roll back. Isolation levels (read uncommitted, read committed, repeatable read, serializable) control concurrency trade-offs.
- **NoSQL Databases:** Non-relational, designed for scale and flexibility.
  - Document stores (MongoDB, Firestore): JSON-like documents, flexible schema.
  - Key-value (Redis, DynamoDB): Extremely fast lookups, simple structure.
  - Column-family (Cassandra, HBase): High write throughput, time series.
  - Graph (Neo4j): Nodes and edges, traversal queries, social networks.
- **Database Design:** Entity-Relationship (ER) diagrams model data. Identify entities, attributes, and relationships (one-to-one, one-to-many, many-to-many). Primary keys, foreign keys, constraints.
- **Query Optimization:** EXPLAIN plans show how the query engine executes queries. Identify full table scans, missing indexes, N+1 queries. Caching layers (Redis) reduce database load.

## CAP Theorem Applied
- SQL (ACID): Prefers consistency and partition tolerance.
- Cassandra: Prefers availability and partition tolerance.
- Redis: Prefers consistency and availability.

## Practical Applications
- **Web apps:** PostgreSQL or MySQL for relational data; Redis for session cache.
- **Real-time analytics:** ClickHouse, BigQuery for OLAP workloads.
- **Event sourcing:** Append-only event log as source of truth.
- **Search:** Elasticsearch for full-text search, faceted filtering.
- **Mobile:** SQLite for local storage; sync to cloud database.
