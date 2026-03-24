# Modern C++ (C++17/20/23)

## C++17 Key Features

### Structured Bindings
```cpp
auto [x, y, z] = std::tuple{1, 2.0, "hello"};
for (auto& [key, value] : map) { /* ... */ }
auto [it, inserted] = set.insert(element);
```

### std::optional
```cpp
std::optional<User> findUser(int id) {
  if (auto it = db.find(id); it != db.end()) return it->second;
  return std::nullopt;
}
auto user = findUser(42);
if (user) process(*user);                           // dereference
user.value_or(defaultUser);                         // fallback
user.transform([](User u) { return u.name; });      // C++23 monadic
```

### std::variant (type-safe union)
```cpp
using Shape = std::variant<Circle, Rectangle, Triangle>;
Shape s = Circle{5.0};
std::visit(overloaded{
  [](Circle c) { return M_PI * c.r * c.r; },
  [](Rectangle r) { return r.w * r.h; },
  [](Triangle t) { return 0.5 * t.b * t.h; }
}, s);
```

## C++20 Key Features

### Concepts (constrain templates)
```cpp
template<typename T>
concept Numeric = std::integral<T> || std::floating_point<T>;

template<Numeric T>
T add(T a, T b) { return a + b; }
// Better error messages vs. SFINAE
```

### Ranges
```cpp
#include <ranges>
auto result = data
  | std::views::filter([](int x) { return x > 0; })
  | std::views::transform([](int x) { return x * x; })
  | std::views::take(10);
// Lazy — nothing computed until iterated
```

### Coroutines (C++20)
```cpp
Generator<int> fibonacci() {
  int a = 0, b = 1;
  while (true) { co_yield a; std::tie(a, b) = {b, a + b}; }
}
// co_await, co_yield, co_return keywords
```

### std::format (C++20) / std::print (C++23)
```cpp
auto s = std::format("Hello, {}! You are {} years old.", name, age);
std::print("Value: {:.2f}\n", 3.14159);  // C++23
```

## Smart Pointers (RAII)
```cpp
// unique_ptr — sole ownership, zero overhead
auto ptr = std::make_unique<Widget>(args);
// Automatically deleted when out of scope

// shared_ptr — shared ownership, reference counting
auto sp = std::make_shared<Resource>();
auto sp2 = sp;  // ref count = 2

// weak_ptr — observe without owning (break cycles)
std::weak_ptr<Node> parent;  // in tree/graph nodes
if (auto locked = parent.lock()) { /* use it */ }
```
Rule: **never use raw `new`/`delete`** in modern C++. Always use smart pointers or containers.

## RAII (Resource Acquisition Is Initialization)
```cpp
class FileGuard {
  FILE* f;
public:
  explicit FileGuard(const char* path) : f(fopen(path, "r")) {
    if (!f) throw std::runtime_error("Cannot open file");
  }
  ~FileGuard() { if (f) fclose(f); }
  // Non-copyable, moveable
  FileGuard(const FileGuard&) = delete;
  FileGuard(FileGuard&& o) noexcept : f(std::exchange(o.f, nullptr)) {}
};
```
RAII ensures cleanup even on exceptions. Applied to: files, locks, network connections, GPU resources.

## Move Semantics
```cpp
std::string makeString() { return std::string(1000, 'x'); }  // NRVO or move
void process(std::string&& s);          // rvalue reference — accepts temporaries
process(std::move(existingStr));        // explicit move — existingStr is valid-but-unspecified after

// Move constructor
Widget(Widget&& other) noexcept
  : data_(std::exchange(other.data_, nullptr)) {}
```
Rule: mark move constructors/assignments `noexcept` — enables optimizations in standard containers.

## Template Metaprogramming Basics
```cpp
// Type trait
template<typename T> struct is_pointer : std::false_type {};
template<typename T> struct is_pointer<T*> : std::true_type {};

// if constexpr (C++17 — compile-time branching)
template<typename T>
void serialize(T value) {
  if constexpr (std::is_integral_v<T>) writeInt(value);
  else if constexpr (std::is_floating_point_v<T>) writeFloat(value);
}
```

## When C++ vs Rust vs Go
| Criteria | C++ | Rust | Go |
|----------|-----|------|----|
| Max performance + legacy | ✅ | ✅ | ❌ |
| Memory safety guarantees | ❌ (UB risk) | ✅ (compiler-enforced) | ✅ (GC) |
| Systems programming (OS, drivers) | ✅ | ✅ | ❌ |
| Concurrency model | Manual (std::thread) | Fearless (ownership) | Goroutines (simple) |
| Learning curve | Very high | High | Low |
| Ecosystem / libraries | Largest (decades) | Growing fast | Strong for services |
| Use cases | Games, HPC, embedded, finance | OS, WebAssembly, security | Microservices, CLIs, DevOps |
