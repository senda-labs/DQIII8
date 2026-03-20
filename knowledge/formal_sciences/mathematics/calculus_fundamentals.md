# Calculus Fundamentals

## Definition
Calculus is the mathematical study of continuous change. It has two major branches: differential calculus (rates of change, slopes of curves) and integral calculus (accumulation of quantities, areas under curves). Both are unified by the Fundamental Theorem of Calculus.

## Core Concepts

- **Limits:** The foundation of calculus. lim(x→a) f(x) = L means f(x) approaches L as x approaches a. Used to define continuity, derivatives, and integrals.
- **Derivatives:** Measure instantaneous rate of change. f'(x) = lim(h→0) [f(x+h) - f(x)] / h. Geometrically: slope of tangent line. Key rules: power rule, product rule, quotient rule, chain rule.
- **Integrals:** Measure accumulated change or area. Definite integral ∫[a,b] f(x)dx = limit of Riemann sums. Indefinite integral ∫f(x)dx = antiderivative F(x) + C.
- **Fundamental Theorem of Calculus:** Links differentiation and integration. If F'(x) = f(x), then ∫[a,b] f(x)dx = F(b) - F(a).
- **Multivariable Calculus:** Extends to functions of multiple variables. Partial derivatives, gradient (∇f), divergence, curl, multiple integrals, line integrals.
- **Differential Equations:** Equations involving derivatives. Model physical systems — Newton's laws, heat diffusion, population growth. Types: ODE, PDE, separable, linear, first-order, second-order.
- **Series and Sequences:** Taylor series expands functions as infinite polynomials. f(x) = f(a) + f'(a)(x-a) + f''(a)(x-a)^2/2! + ...

## Key Rules
- Power rule: d/dx [x^n] = nx^(n-1)
- Chain rule: d/dx [f(g(x))] = f'(g(x)) * g'(x)
- Integration by parts: ∫u dv = uv - ∫v du

## Practical Applications
- **Physics:** Velocity = derivative of position; acceleration = derivative of velocity.
- **Machine learning:** Gradient descent uses partial derivatives to minimize loss functions.
- **Economics:** Marginal cost and revenue are derivatives of total cost/revenue functions.
- **Engineering:** Integral calculus for work, flux, electric fields.
- **Finance:** Black-Scholes option pricing uses stochastic differential equations.
