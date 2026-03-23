---
domain: applied_sciences
type: reference_data
last_updated: 2026-03
keywords_en: [algorithm complexity, Big O, benchmark, latency, throughput, framework, React, Vue, database, PostgreSQL, Redis, AWS, cloud, performance, sorting, search]
keywords_es: [complejidad algorítmica, Big O, benchmark, latencia, rendimiento, framework, base de datos, PostgreSQL, Redis, AWS, nube, ordenación]
---

# Performance Benchmarks & Complexity Reference

## Algorithm Complexity Cheatsheet (Big O)

### Sorting Algorithms

| Algorithm | Best | Average | Worst | Space | Stable | Notes |
|-----------|------|---------|-------|-------|--------|-------|
| Quicksort | O(n log n) | O(n log n) | O(n²) | O(log n) | No | In-place; pivot matters |
| Mergesort | O(n log n) | O(n log n) | O(n log n) | O(n) | Yes | Guaranteed; external sort |
| Heapsort | O(n log n) | O(n log n) | O(n log n) | O(1) | No | In-place but poor cache |
| Timsort | O(n) | O(n log n) | O(n log n) | O(n) | Yes | Python/Java default |
| Insertion Sort | O(n) | O(n²) | O(n²) | O(1) | Yes | Fast for n<16; Timsort base |
| Counting Sort | O(n+k) | O(n+k) | O(n+k) | O(k) | Yes | k = range of values |
| Radix Sort | O(nk) | O(nk) | O(nk) | O(n+k) | Yes | k = number of digits |

Practical crossover: Insertion sort beats quicksort for n≤10–16 elements.

### Searching & Data Structure Operations

| Structure / Op | Access | Search | Insert | Delete | Space |
|----------------|--------|--------|--------|--------|-------|
| Array | O(1) | O(n) | O(n) | O(n) | O(n) |
| Linked List | O(n) | O(n) | O(1) | O(1) | O(n) |
| Hash Table | — | O(1)* | O(1)* | O(1)* | O(n) |
| BST (balanced) | O(log n) | O(log n) | O(log n) | O(log n) | O(n) |
| BST (worst) | O(n) | O(n) | O(n) | O(n) | O(n) |
| Red-Black Tree | O(log n) | O(log n) | O(log n) | O(log n) | O(n) |
| B-Tree (t order) | O(log n) | O(log n) | O(log n) | O(log n) | O(n) |
| Binary Heap | O(1) top | O(n) | O(log n) | O(log n) | O(n) |
| Trie | — | O(m) | O(m) | O(m) | O(n·m) |

*Hash table amortized O(1); worst case O(n) due to collisions.

### Graph Algorithms

| Algorithm | Time | Space | Use Case |
|-----------|------|-------|----------|
| BFS | O(V+E) | O(V) | Shortest path (unweighted), level order |
| DFS | O(V+E) | O(V) | Cycle detection, topological sort |
| Dijkstra (binary heap) | O((V+E) log V) | O(V) | Shortest path, non-negative weights |
| Bellman-Ford | O(VE) | O(V) | Negative weights; detects negative cycles |
| Floyd-Warshall | O(V³) | O(V²) | All-pairs shortest path; small graphs |
| Kruskal | O(E log E) | O(V) | Minimum spanning tree |
| Prim (binary heap) | O(E log V) | O(V) | Minimum spanning tree; dense graphs |
| Topological Sort | O(V+E) | O(V) | DAG ordering (build systems, tasks) |
| Tarjan's SCC | O(V+E) | O(V) | Strongly connected components |

Practical limit: Dijkstra handles ~10M edges in <1s; Floyd-Warshall: ~3000 nodes in <1s.

## Database Performance Benchmarks

### PostgreSQL Query Performance (typical, well-indexed)

| Operation | Rows Affected | Approx Time | Notes |
|-----------|--------------|-------------|-------|
| SELECT (indexed PK) | 1 | <1 ms | Single B-tree lookup |
| SELECT (seq scan) | 1M rows | 200–800 ms | Full table, no index |
| SELECT (index scan) | 10K rows | 5–20 ms | B-tree index on filter col |
| SELECT (index range) | 100K rows | 20–80 ms | Range predicate with index |
| INSERT (single) | 1 | <1 ms | No triggers |
| INSERT (bulk, COPY) | 1M rows | 2–8 s | COPY FROM fastest |
| UPDATE (indexed) | 10K rows | 50–200 ms | With WHERE on indexed col |
| DELETE (indexed) | 10K rows | 50–200 ms | Cascades add latency |
| CREATE INDEX (B-tree) | 1M rows | 5–30 s | Depends on row size |
| VACUUM ANALYZE | 1M rows | 10–60 s | Depends on dead tuples |

### PostgreSQL vs MySQL vs SQLite (TPC-H Scale Factor 1, 2024)

| DB | Query 1 (aggreg.) | Query 6 (scan) | Query 9 (join) | Storage (1GB data) |
|----|------------------|---------------|-----------------|-------------------|
| PostgreSQL 16 | 0.45s | 0.18s | 2.1s | 540 MB |
| MySQL 8.0 | 0.62s | 0.24s | 3.4s | 650 MB |
| SQLite 3.45 | 1.20s | 0.55s | 5.8s | 580 MB |
| DuckDB 0.10 | 0.08s | 0.03s | 0.4s | 220 MB (columnar) |

### Redis Throughput (single-node, commodity HW, 2024)

| Operation | Throughput (ops/s) | Latency p99 | Notes |
|-----------|-------------------|-------------|-------|
| GET | ~110,000 | <1 ms | Single key |
| SET | ~85,000 | <1 ms | Single key |
| HSET | ~75,000 | <1 ms | Hash field |
| LPUSH | ~80,000 | <1 ms | List prepend |
| ZADD | ~60,000 | <1 ms | Sorted set |
| Pipeline (GET×100) | ~1,200,000 | 2–5 ms | Batch reduces RTT |

Redis 7.x cluster: linear scaling up to ~8 nodes. Memory overhead: ~50 bytes/key base.

## Cloud Service Latencies (global averages, 2024–2025)

### AWS Service Latencies (us-east-1 baseline)

| Service | Operation | p50 | p95 | p99 |
|---------|-----------|-----|-----|-----|
| DynamoDB | GetItem | 2 ms | 6 ms | 15 ms |
| DynamoDB | Query (10 items) | 4 ms | 9 ms | 25 ms |
| S3 | GetObject (<1MB) | 15 ms | 40 ms | 80 ms |
| S3 | PutObject (<1MB) | 18 ms | 50 ms | 100 ms |
| ElastiCache (Redis) | GET | <1 ms | 2 ms | 5 ms |
| RDS PostgreSQL | Simple SELECT | 3 ms | 8 ms | 20 ms |
| Lambda | Cold start (Python) | 200 ms | 700 ms | 1500 ms |
| Lambda | Warm invocation | 2 ms | 10 ms | 25 ms |
| API Gateway | HTTP proxy | 10 ms | 25 ms | 60 ms |
| SQS | SendMessage | 5 ms | 12 ms | 30 ms |

### Cross-Region Latency (AWS, 2024)

| Route | RTT |
|-------|-----|
| us-east-1 → us-west-2 | ~62 ms |
| us-east-1 → eu-west-1 | ~88 ms |
| us-east-1 → ap-southeast-1 | ~175 ms |
| eu-west-1 → ap-northeast-1 | ~210 ms |
| us-west-2 → ap-northeast-1 | ~125 ms |

## Frontend Framework Benchmarks (JS Framework Benchmark, 2024)

### js-framework-benchmark v8 — Chrome 121, M3 MacBook

| Framework | Create 1k rows (ms) | Update every 10th (ms) | Select row (ms) | Memory (MB) |
|-----------|--------------------|-----------------------|-----------------|-------------|
| Vanilla JS | 47 | 42 | 7 | 3.2 |
| Solid.js 1.8 | 52 | 45 | 8 | 3.8 |
| Preact 10 | 58 | 50 | 9 | 4.1 |
| Vue 3.4 | 65 | 56 | 11 | 5.3 |
| Svelte 4 | 60 | 54 | 10 | 4.5 |
| React 18 | 75 | 68 | 13 | 6.2 |
| Angular 17 | 82 | 75 | 15 | 8.4 |
| Ember 5 | 155 | 134 | 22 | 14.8 |

Lower is better. React with concurrent mode adds ~5ms overhead vs legacy mode.

### HTTP Server Throughput (Techempower Plaintext, Round 22, 2024)

| Framework | Lang | RPS (req/s) | Latency p99 |
|-----------|------|-------------|-------------|
| Actix-web 4 | Rust | 7,230,000 | <1 ms |
| ntex | Rust | 6,890,000 | <1 ms |
| Hyper | Rust | 6,540,000 | <1 ms |
| Bun.js HTTP | JS | 2,100,000 | 1 ms |
| Fastify 4 | Node.js | 890,000 | 2 ms |
| Express 4 | Node.js | 320,000 | 5 ms |
| FastAPI (uvicorn) | Python | 270,000 | 5 ms |
| Axum | Rust | 6,100,000 | <1 ms |
| Gin | Go | 1,400,000 | 1 ms |
| Echo | Go | 1,350,000 | 1 ms |
| Spring Boot 3 | Java | 950,000 | 2 ms |
| Django 4.2 | Python | 45,000 | 15 ms |

## LLM Inference Performance (2024–2025)

### Tokens per Second (generation, single A100 80GB)

| Model | Size | Backend | Output tok/s | VRAM |
|-------|------|---------|-------------|------|
| Llama 3.1 8B | 8B | vLLM | ~120 tok/s | 16 GB |
| Llama 3.1 70B | 70B | vLLM (×4 A100) | ~35 tok/s | 4×80 GB |
| Qwen2.5-Coder 7B | 7B | Ollama (CPU) | ~8 tok/s | 8 GB RAM |
| Qwen2.5-Coder 7B | 7B | Ollama (A100) | ~85 tok/s | 8 GB VRAM |
| Mistral 7B | 7B | vLLM | ~110 tok/s | 14 GB |
| GPT-4o (API) | — | OpenAI | ~80 tok/s | — |
| Claude Sonnet 4.6 (API) | — | Anthropic | ~100 tok/s | — |
| Gemini 1.5 Flash (API) | — | Google | ~150 tok/s | — |

### API Provider Pricing Comparison (mid-2025, per MTok)

| Model | Input | Output | Context | Notes |
|-------|-------|--------|---------|-------|
| GPT-4o | $2.50 | $10.00 | 128K | OpenAI |
| GPT-4o mini | $0.15 | $0.60 | 128K | OpenAI |
| Claude Sonnet 4.6 | $3.00 | $15.00 | 200K | Anthropic |
| Claude Haiku 4.5 | $0.80 | $4.00 | 200K | Anthropic |
| Gemini 1.5 Flash | $0.075 | $0.30 | 1M | Google |
| Gemini 1.5 Pro | $1.25 | $5.00 | 2M | Google |
| Llama 3.3 70B (Groq) | $0.00 | $0.00 | 32K | Free tier; 100K TPD |
| Llama 3.3 70B (Together) | $0.18 | $0.88 | 32K | Together AI |
| Deepseek V3 | $0.27 | $1.10 | 128K | Deepseek |
