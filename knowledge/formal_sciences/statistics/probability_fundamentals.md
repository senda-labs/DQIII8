# Probability Fundamentals

## Definition
Probability theory is the mathematical framework for quantifying uncertainty and reasoning about random events. It assigns numerical values between 0 and 1 to events, where 0 indicates impossibility and 1 indicates certainty.

## Core Concepts

- **Sample Space and Events:** The sample space S is the set of all possible outcomes. An event A is a subset of S. P(A) = |A| / |S| for uniform distributions.
- **Probability Axioms (Kolmogorov):** P(S) = 1; P(A) >= 0 for all events A; P(A ∪ B) = P(A) + P(B) if A and B are mutually exclusive.
- **Conditional Probability:** P(A|B) = P(A ∩ B) / P(B). Probability of A given B has occurred.
- **Bayes' Theorem:** P(A|B) = P(B|A) * P(A) / P(B). Fundamental for updating beliefs with new evidence. Basis of Bayesian inference.
- **Independence:** Events A and B are independent if P(A ∩ B) = P(A) * P(B). Knowing B occurred gives no information about A.
- **Random Variables:** Functions mapping outcomes to numerical values. Discrete RVs have probability mass functions (PMF); continuous RVs have probability density functions (PDF).
- **Expectation and Variance:** E[X] = sum of x * P(X=x) (discrete) or integral of x * f(x)dx (continuous). Var(X) = E[(X - E[X])^2] = E[X^2] - (E[X])^2.
- **Key Distributions:** Bernoulli, Binomial, Poisson, Normal (Gaussian), Exponential, Uniform, Beta, Gamma.

## Key Results
- Law of Total Probability: P(A) = sum P(A|B_i) * P(B_i)
- Central Limit Theorem: sum of n i.i.d. RVs approaches Normal as n → ∞
- Law of Large Numbers: sample mean → population mean as n → ∞
- Chebyshev's inequality: P(|X - μ| >= kσ) <= 1/k^2

## Practical Applications
- **Machine learning:** Probabilistic models, Naive Bayes classifiers, Bayesian networks.
- **Finance:** Risk models, option pricing, portfolio variance.
- **A/B testing:** Determining statistical significance of experimental results.
- **Spam filters:** Bayesian classifiers compute P(spam | words).
- **Quality control:** Acceptance sampling, process control charts.
