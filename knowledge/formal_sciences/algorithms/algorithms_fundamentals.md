# Algorithms Fundamentals

## Definition
An algorithm is a finite, ordered sequence of well-defined instructions for solving a problem or accomplishing a task. Algorithm analysis studies correctness (does it produce the right answer?) and efficiency (how much time and space does it consume?).

## Core Concepts

- **Time Complexity:** How running time grows with input size n. Expressed in Big-O notation. O(1) constant, O(log n) logarithmic, O(n) linear, O(n log n) linearithmic, O(n^2) quadratic, O(2^n) exponential.
- **Space Complexity:** Memory usage as a function of input size. Often a trade-off with time (e.g., memoization uses more space to reduce time).
- **Divide and Conquer:** Split problem into subproblems, solve recursively, combine. Examples: merge sort O(n log n), binary search O(log n), fast Fourier transform.
- **Dynamic Programming:** Solve overlapping subproblems once and store results (memoization/tabulation). Examples: Fibonacci, longest common subsequence, knapsack, shortest paths.
- **Greedy Algorithms:** Make locally optimal choices at each step. Work when a greedy choice property holds. Examples: Dijkstra's shortest path, Huffman coding, activity selection.
- **Graph Algorithms:** BFS (shortest path in unweighted graphs), DFS (cycle detection, topological sort), Dijkstra (weighted shortest path), Bellman-Ford (negative weights), Floyd-Warshall (all pairs).
- **Sorting:** Comparison sorts (merge sort, quicksort, heapsort) are O(n log n) lower bound. Non-comparison sorts (counting sort, radix sort) can be O(n).
- **Backtracking:** Explore all possibilities by building solutions incrementally, abandoning invalid paths. Examples: N-queens, Sudoku solver, subset sum.

## Key Theorems
- Master Theorem: Solves recurrences T(n) = aT(n/b) + f(n)
- Lower bound for comparison-based sorting: Omega(n log n)
- P vs NP: Fundamental open problem in computer science

## Practical Applications
- **Search engines:** PageRank (graph algorithm), inverted index search.
- **GPS navigation:** Dijkstra / A* for shortest paths.
- **Compression:** Huffman coding, LZ77 (deflate/gzip).
- **Machine learning:** Gradient descent optimization, decision tree construction.
- **Databases:** B-tree indexing, query optimization.
