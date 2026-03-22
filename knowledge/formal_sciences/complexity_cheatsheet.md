---
domain: formal_sciences
agent: algo-specialist
keywords_es: [complejidad, Big-O, estructura datos, amortizado, NP-completo, array, hash, heap, árbol, grafo, ordenamiento]
keywords_en: [complexity, Big-O, data structure, amortized, NP-complete, array, hash, heap, tree, graph, sorting]
---

# Complexity Cheatsheet — Data Structures & Algorithms

## Data Structures

| Structure | Access | Search | Insert | Delete | Space | Notes |
|-----------|--------|--------|--------|--------|-------|-------|
| Array (static) | O(1) | O(n) | O(n) | O(n) | O(n) | contiguous memory, cache-friendly |
| Dynamic Array | O(1) | O(n) | O(1)* | O(n) | O(n) | *amortized; doubling strategy |
| Singly Linked List | O(n) | O(n) | O(1) head | O(1) with ref | O(n) | no random access |
| Doubly Linked List | O(n) | O(n) | O(1) | O(1) with ref | O(n) | O(1) insert/delete at known node |
| Stack (array-based) | O(n) | O(n) | O(1)* | O(1) | O(n) | push/pop at top |
| Queue (deque) | O(n) | O(n) | O(1) | O(1) | O(n) | enqueue/dequeue |
| Hash Table | N/A | O(1) avg O(n) worst | O(1) avg | O(1) avg | O(n) | load factor < 0.75 (Java); resize at 0.7 (Python) |
| BST (unbalanced) | O(log n) avg O(n) | O(log n) avg O(n) | O(log n) avg O(n) | O(log n) avg O(n) | O(n) | degrades to O(n) when sorted input |
| AVL Tree | O(log n) | O(log n) | O(log n) | O(log n) | O(n) | height <= 1.44 log2(n); <=2 rotations insert |
| Red-Black Tree | O(log n) | O(log n) | O(log n) | O(log n) | O(n) | height <= 2*log2(n+1); <=3 rotations delete |
| B-Tree (order m) | O(log_m n) | O(log_m n) | O(log_m n) | O(log_m n) | O(n) | m-1 keys per node; disk IO optimized |
| Binary Heap | O(1) min/max | O(n) | O(log n) | O(log n) | O(n) | array-based; heapify O(n) from array |
| Fibonacci Heap | O(1) | O(n) | O(1) amort | O(log n) amort | O(n) | decrease-key O(1); used in Dijkstra |
| Trie | O(k) | O(k) | O(k) | O(k) | O(ALPHA*k*n) | k=key length; ALPHA=alphabet size |
| Segment Tree | O(n) build | O(log n) range query | O(log n) point update | O(log n) | O(4n) | range sum/min/max queries |
| Fenwick Tree (BIT) | — | O(log n) prefix sum | O(log n) point update | O(log n) | O(n) | simpler than segment tree; prefix sums only |
| Disjoint Set (DSU) | — | O(alpha(n)) find | O(alpha(n)) union | N/A | O(n) | alpha=inverse Ackermann; path compression + union by rank |
| Sparse Table | O(1) | O(1) range query | O(n log n) build | N/A | O(n log n) | read-only; RMQ in O(1) |
| Skip List | O(log n) avg | O(log n) avg | O(log n) avg | O(log n) avg | O(n log n) | probabilistic; simpler than balanced BST |

**DSU amortized alpha(n) is effectively constant for all practical n (n < 10^80).**

## Sorting Algorithms

| Algorithm | Best | Average | Worst | Space | Stable | Notes |
|-----------|------|---------|-------|-------|--------|-------|
| Bubble Sort | O(n) | O(n²) | O(n²) | O(1) | Yes | never use in practice |
| Insertion Sort | O(n) | O(n²) | O(n²) | O(1) | Yes | best for n<20 or nearly sorted |
| Selection Sort | O(n²) | O(n²) | O(n²) | O(1) | No | minimal swaps (useful for slow write media) |
| Merge Sort | O(n log n) | O(n log n) | O(n log n) | O(n) | Yes | external sort; guaranteed |
| Quicksort | O(n log n) | O(n log n) | O(n²) | O(log n) | No | O(n²) on sorted input without median-of-3 |
| Heapsort | O(n log n) | O(n log n) | O(n log n) | O(1) | No | in-place but poor cache behavior |
| Timsort | O(n) | O(n log n) | O(n log n) | O(n) | Yes | Python/Java default; detects natural runs |
| Introsort | O(n log n) | O(n log n) | O(n log n) | O(log n) | No | C++ std::sort; quicksort + heapsort fallback |
| Counting Sort | O(n+k) | O(n+k) | O(n+k) | O(k) | Yes | k=value range; integers only |
| Radix Sort (LSD) | O(nk) | O(nk) | O(nk) | O(n+k) | Yes | k=number of digits |
| Bucket Sort | O(n+k) | O(n+k) | O(n²) | O(n+k) | Yes | uniform distribution; worst if all same bucket |
| Shell Sort | O(n log n) | O(n^1.3) | O(n²) | O(1) | No | depends on gap sequence |

## Graph Algorithm Complexity

| Algorithm | Time | Space | Use Case |
|-----------|------|-------|----------|
| BFS | O(V+E) | O(V) | shortest path unweighted, level order |
| DFS | O(V+E) | O(V) | cycle detection, topological sort, SCC |
| Dijkstra (binary heap) | O((V+E) log V) | O(V) | SSSP non-negative weights |
| Dijkstra (Fibonacci heap) | O(E + V log V) | O(V) | dense graphs with E >> V |
| Bellman-Ford | O(VE) | O(V) | negative weights; detects negative cycles |
| A* | O(E) avg | O(V) | heuristic-guided; admissible heuristic required |
| Floyd-Warshall | O(V³) | O(V²) | APSP; dense graphs |
| Kruskal MST | O(E log E) | O(V) | sparse graphs |
| Prim MST (binary heap) | O(E log V) | O(V) | dense graphs |
| Topological Sort (Kahn) | O(V+E) | O(V) | DAG ordering |
| Tarjan SCC | O(V+E) | O(V) | strongly connected components |
| Kosaraju SCC | O(V+E) | O(V) | 2 DFS passes |

## NP-Completeness Reference

- **P** = solvable in polynomial time
- **NP** = verifiable in polynomial time
- **NP-Hard** = at least as hard as all NP problems (not necessarily in NP)
- **NP-Complete** = in NP AND NP-Hard

Classic NP-Complete: SAT, 3-SAT, Clique, Vertex Cover, Hamiltonian Cycle, TSP (decision), Graph Coloring (k>=3), Subset Sum, Knapsack (0/1)

Reductions direction: 3-SAT -> Clique -> Vertex Cover -> Independent Set

**Source:** Cormen et al. "Introduction to Algorithms" (CLRS) 4th ed. + competitive programming references (cp-algorithms.com)
