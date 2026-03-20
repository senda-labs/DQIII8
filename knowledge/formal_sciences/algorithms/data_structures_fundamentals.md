# Data Structures Fundamentals

## Definition
Data structures are ways of organizing and storing data so that it can be accessed and modified efficiently. Choosing the right data structure is fundamental to algorithm performance and system design.

## Core Concepts

- **Arrays:** Contiguous memory blocks. O(1) random access by index, O(n) insertion/deletion in the middle. Foundation for most other structures.
- **Linked Lists:** Nodes containing data and pointers to next/previous nodes. O(1) insertion/deletion at known position, O(n) access by index. Singly, doubly, circular variants.
- **Stacks:** LIFO (Last In, First Out). Operations: push, pop, peek. Applications: function call stack, undo operations, expression parsing.
- **Queues:** FIFO (First In, First Out). Operations: enqueue, dequeue. Variants: deque (double-ended), priority queue (heap-based). Applications: BFS, task scheduling.
- **Hash Tables:** Key-value storage with O(1) average-case lookup, insert, delete. Uses hash functions to map keys to bucket indices. Collision handling: chaining, open addressing.
- **Trees:** Hierarchical structures. Binary Search Tree: O(log n) search/insert when balanced. AVL, Red-Black trees maintain balance automatically. B-trees used in databases.
- **Heaps:** Complete binary tree satisfying the heap property (max-heap: parent >= children). O(log n) insert and extract-max. Used for priority queues and heapsort.
- **Graphs:** Nodes (vertices) and edges. Represented as adjacency list (sparse) or adjacency matrix (dense). Used to model networks, dependencies, state machines.
- **Tries:** Prefix trees for string operations. O(m) lookup where m = string length. Used in autocomplete, spell checkers, IP routing.

## Complexity Summary
| Structure | Access | Search | Insert | Delete |
|-----------|--------|--------|--------|--------|
| Array | O(1) | O(n) | O(n) | O(n) |
| Hash Table | N/A | O(1) avg | O(1) avg | O(1) avg |
| BST | O(log n) | O(log n) | O(log n) | O(log n) |
| Heap | O(1) top | O(n) | O(log n) | O(log n) |

## Practical Applications
- **Databases:** B-trees for indexes, hash maps for joins.
- **Caching:** Hash tables (Redis, Memcached), LRU cache (doubly linked list + hash map).
- **Compilers:** Symbol tables (hash tables), abstract syntax trees.
- **Networking:** Routing tables (tries), packet queues.
- **Operating systems:** Process scheduling (priority queues), file systems (trees).
