---
domain: applied_sciences
agent: data-specialist
keywords_es: [SQL, window function, CTE, índice, normalización, optimización, query plan, PostgreSQL, JOIN, EXPLAIN, partición, índice GIN]
keywords_en: [SQL, window function, CTE, index, normalization, optimization, query plan, PostgreSQL, JOIN, EXPLAIN, partition, GIN index]
---

# SQL Advanced Patterns Reference

## Window Functions — Complete Reference

```sql
-- Basic syntax
function_name() OVER (
  [PARTITION BY col]
  [ORDER BY col]
  [ROWS/RANGE BETWEEN frame_start AND frame_end]
)

-- Frame clauses:
-- ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW  → cumulative
-- ROWS BETWEEN 6 PRECEDING AND CURRENT ROW           → rolling 7-row window
-- ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING → window over whole partition
```

| Function | Description | Example Use |
|----------|-------------|------------|
| ROW_NUMBER() | Sequential rank, no ties | Pagination; deduplication |
| RANK() | Rank with ties; gaps after tied rows (1,1,3) | Competitions |
| DENSE_RANK() | Rank with ties; no gaps (1,1,2) | Top-N with ties |
| NTILE(n) | Divide into n equal buckets | Quartiles, deciles |
| LAG(col, n, default) | Value n rows before current | Period-over-period comparison |
| LEAD(col, n, default) | Value n rows after current | Next event analysis |
| FIRST_VALUE(col) | First value in frame | Baseline comparison |
| LAST_VALUE(col) | Last value in frame (needs explicit frame!) | Current state |
| NTH_VALUE(col, n) | Nth value in frame | Arbitrary position |
| SUM() OVER() | Running/rolling sum | Cumulative revenue |
| AVG() OVER() | Running/rolling average | Moving average |
| COUNT() OVER() | Running/rolling count | Cumulative count |
| PERCENT_RANK() | (rank-1)/(rows-1); 0 to 1 | Percentile position |
| CUME_DIST() | Cumulative distribution; 0 to 1 | Distribution analysis |

**Common mistake:** LAST_VALUE without explicit frame defaults to ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW — returns current row's value. Fix: use `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING`.

## Recursive CTE Example

```sql
-- Organizational hierarchy traversal
WITH RECURSIVE org_hierarchy AS (
  -- Anchor: top-level (no manager)
  SELECT
    id, name, manager_id,
    0 AS depth,
    ARRAY[id] AS path,
    name::TEXT AS full_path
  FROM employees
  WHERE manager_id IS NULL

  UNION ALL

  -- Recursive: employees reporting to someone in the CTE
  SELECT
    e.id, e.name, e.manager_id,
    h.depth + 1,
    h.path || e.id,
    h.full_path || ' > ' || e.name
  FROM employees e
  JOIN org_hierarchy h ON e.manager_id = h.id
  WHERE e.id != ALL(h.path)  -- cycle protection
)
SELECT * FROM org_hierarchy ORDER BY path;
```

```sql
-- Running 7-day average (time series)
SELECT
  date,
  revenue,
  AVG(revenue) OVER (
    ORDER BY date
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
  ) AS rolling_7day_avg,
  SUM(revenue) OVER (
    ORDER BY date
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
  ) AS cumulative_revenue
FROM daily_sales;
```

## Normalization Decision Tree

```
1NF: No repeating groups; each cell atomic; each row unique
  Violation: tags = "python,sql,java" → separate tags table

2NF (applies only if composite PK): No partial dependency
  Violation: (student_id, course_id) → instructor_name
  instructor_name depends only on course_id, not full PK

3NF: No transitive dependencies
  Violation: employee_id → department_id → department_name
  Solution: separate departments table

BCNF: Every determinant is a candidate key
  Stricter than 3NF; rarely matters in practice

When to DENORMALIZE:
  - Read-heavy analytics tables (star/snowflake schema)
  - Reporting tables with <5% write rate
  - Pre-aggregated summary tables
  - When JOINs become performance bottleneck (>8 tables, millions of rows)
```

## PostgreSQL Index Types

| Index Type | Best For | NOT For | Notes |
|------------|---------|---------|-------|
| B-tree (default) | =, <, <=, >, >=, BETWEEN, IN, LIKE 'prefix%', IS NULL, ORDER BY | LIKE '%suffix', full text | Default; covers most cases |
| Hash | Only = comparison | Ranges, ordering | No WAL logging pre-v10; rarely better than B-tree |
| GIN | JSONB containment (@>, ?), arrays, full-text (tsvector) | Single value lookups | Slow write; fast read; good for multi-valued types |
| GiST | Geometry (PostGIS), ranges (daterange), full-text | Exact equality | Lossy (recheck required); flexible framework |
| BRIN | Naturally ordered data (timestamps, auto-increment IDs) | Random data | Extremely compact (min/max per block range); 1000x smaller than B-tree |
| SP-GiST | Non-balanced data; IP ranges; phone numbers | General purpose | Space-partitioned GiST; good for sparse data |

## EXPLAIN / EXPLAIN ANALYZE Output

```
EXPLAIN ANALYZE SELECT * FROM orders WHERE customer_id = 123;

Seq Scan on orders (cost=0.00..1234.00 rows=1 width=64)
                             ^startup ^total  ^estimated_rows
  (actual time=0.012..15.432 rows=47 loops=1)
               ^first_row   ^last_row ^actual

Scan nodes (worst → best for large tables):
  Seq Scan: reads entire table → add index
  Index Scan: uses index; fetches heap rows → good
  Index Only Scan: index covers all needed cols → best
  Bitmap Heap Scan: multiple index values → good for range queries

Join algorithms:
  Nested Loop: good for small tables or indexed inner
  Hash Join: good for large unsorted inputs; uses memory
  Merge Join: good if both inputs already sorted

Key EXPLAIN metrics:
  cost: arbitrary units (page reads); ratio matters more than absolute
  rows: estimated; if wildly wrong → run ANALYZE tablename
  actual time: milliseconds; compare startup vs total
  loops: multiplied by actual for true total
  buffers: EXPLAIN (ANALYZE, BUFFERS) → hit=cache, read=disk
```

## Common Optimization Patterns

```sql
-- Use EXISTS over IN for subqueries (stops at first match)
-- WRONG: SELECT * FROM a WHERE id IN (SELECT a_id FROM b WHERE active=true)
-- RIGHT: SELECT * FROM a WHERE EXISTS (SELECT 1 FROM b WHERE b.a_id=a.id AND b.active=true)

-- Partial index (index only relevant subset)
CREATE INDEX idx_active_users ON users(email) WHERE is_active = true;

-- Covering index (include all SELECT columns to avoid heap fetch)
CREATE INDEX idx_orders_customer ON orders(customer_id) INCLUDE (total, created_at);

-- Avoid function on indexed column (disables index)
-- WRONG: WHERE LOWER(email) = 'test@test.com'
-- RIGHT: Create functional index: CREATE INDEX ON users(LOWER(email));

-- Pagination: keyset > OFFSET for large pages
-- WRONG (slow at high offset): LIMIT 20 OFFSET 10000
-- RIGHT: WHERE created_at < :last_seen_created_at ORDER BY created_at DESC LIMIT 20
```

**Source:** PostgreSQL 16 Official Documentation (postgresql.org/docs) + "Use The Index, Luke" (use-the-index-luke.com) + Winand "SQL Performance Explained"
