---
domain: formal_sciences
agent: math-specialist
keywords_es: [convergencia, Newton-Raphson, bisección, error numérico, punto fijo, iterativo, Secante, Brent, Müller]
keywords_en: [convergence, Newton-Raphson, bisection, numerical error, fixed point, iterative, Secant, Brent, Muller]
---

# Numerical Methods — Convergence Reference

## Convergence Order Table

| Method | Order | Convergence Condition | Evals/iter | Formula |
|--------|-------|-----------------------|-----------|---------|
| Bisection | 1 (linear) | f continuous, sign change on [a,b] | 1 (f) | x = (a+b)/2 |
| Fixed Point | 1 (linear) | |g'(x*)| < 1 in neighborhood | 1 (g) | x_{n+1} = g(x_n) |
| Secant | ~1.618 (superlinear, golden ratio) | f differentiable near root | 1 (f) | x_{n+1} = x_n - f(x_n)(x_n - x_{n-1})/(f(x_n)-f(x_{n-1})) |
| Regula Falsi | 1 (linear, superlinear in some cases) | f continuous, sign change | 1 (f) | same as secant but keeps bracket |
| Newton-Raphson | 2 (quadratic) | f'(x*) != 0, good init | 2 (f + f') | x_{n+1} = x_n - f(x_n)/f'(x_n) |
| Halley | 3 (cubic) | requires f, f', f'' | 3 | x_{n+1} = x_n - f·f' / (f'^2 - f·f''/2) |
| Müller | ~1.84 | quadratic interpolation through 3 pts | 1 (f) | uses complex arithmetic, finds complex roots |
| Brent | superlinear (guaranteed) | f continuous, sign change | 1-2 (f) | combines bisection + secant + inverse quadratic |

**Key insight LLMs often miss:** Brent's method is the practical default — bisection guarantees convergence, secant provides speed. scipy.optimize.brentq uses Brent.

## IEEE 754 Machine Epsilon

| Type | Bits | Epsilon (u) | Min positive normal | Max |
|------|------|-------------|---------------------|-----|
| float16 | 16 | 9.77e-4 | 6.10e-5 | 65504 |
| float32 | 32 | 1.19e-7 | 1.18e-38 | 3.40e+38 |
| float64 | 64 | 2.22e-16 | 2.23e-308 | 1.80e+308 |
| float128 | 128 | 1.08e-19 | 3.36e-4932 | 1.19e+4932 |

Stopping criterion: |x_{n+1} - x_n| < sqrt(epsilon) * |x_n| + epsilon (NOT just epsilon)

## Catastrophic Cancellation — When It Occurs

Subtraction of nearly-equal numbers: f(x) = (1 - cos x) / x^2 near x=0
- Naive: loses ~14 significant digits at x=1e-8
- Stable: f(x) = 2*sin^2(x/2) / x^2 (trigonometric identity rewrite)

Pattern: a - b when |a - b| << |a|, |b| → use Taylor expansion or algebraic rewrite

## Forward vs Backward Error

| Error Type | Definition | When to Use |
|------------|-----------|-------------|
| Forward error | |x_computed - x_true| | absolute accuracy of result |
| Backward error | |f(x_computed)| | how well computed x satisfies equation |
| Condition number | kappa = |x·f'(x)/f(x)| near root | amplification of input perturbation |

Well-conditioned root: condition number small → forward error ≈ backward error
Ill-conditioned: f'(x*) ≈ 0 (tangential root) → tiny f value, huge x error

## Practical Convergence Diagnostics

```
Check each iteration: ratio = |e_{n+1}| / |e_n|^p
- If ratio → const and p=1: linear convergence (bisection, Gauss-Seidel)
- If ratio → const and p=2: quadratic (Newton)
- If ratio → 0 quickly: superlinear
- If ratio → 1: stagnation / near-convergence issue
```

Max iterations before declaring non-convergence:
- Bisection: ceil(log2((b-a)/tol)) — exact
- Newton/Secant: 50 (if not converged, bad initialization)

**Source:** NIST DLMF (dlmf.nist.gov) + Press et al. "Numerical Recipes" 3rd ed. (2007)
