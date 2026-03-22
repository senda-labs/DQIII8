---
domain: formal_sciences
agent: stats-specialist
keywords_es: [distribución, parámetros, media, varianza, momento, conjugada, MLE, Normal, Poisson, Binomial, Gamma, Beta, exponencial, t-student]
keywords_en: [distribution, parameters, mean, variance, moment, conjugate prior, MLE, Normal, Poisson, Binomial, Gamma, Beta, exponential, t-student]
---

# Probability Distributions — Parameters & Reference

## Core Distributions Table

| Distribution | Params | Support | Mean | Variance | MLE (hat) | Conjugate Prior |
|-------------|--------|---------|------|----------|-----------|-----------------|
| Normal(mu,sigma²) | mu in R, sigma²>0 | R | mu | sigma² | mu=x_bar, sigma²=s²_n | Normal-Inverse-Gamma |
| t(nu) | nu>0 (df) | R | 0 (nu>1), else undef | nu/(nu-2) (nu>2) | — | — |
| Chi²(k) | k>0 (df) | [0,inf) | k | 2k | — | — |
| F(d1,d2) | d1,d2>0 | [0,inf) | d2/(d2-2) (d2>2) | 2d2²(d1+d2-2)/(d1(d2-2)²(d2-4)) | — | — |
| Bernoulli(p) | p in [0,1] | {0,1} | p | p(1-p) | p=x_bar | Beta(alpha,beta) |
| Binomial(n,p) | n>=1, p in [0,1] | {0,...,n} | np | np(1-p) | p=x_bar/n | Beta(alpha,beta) |
| Geometric(p) | p in (0,1] | {1,2,...} | 1/p | (1-p)/p² | p=1/x_bar | Beta(alpha,beta) |
| Negative Binom(r,p) | r>0, p in (0,1) | {r,r+1,...} | r/p | r(1-p)/p² | — | Beta |
| Poisson(lambda) | lambda>0 | {0,1,...} | lambda | lambda | lambda=x_bar | Gamma(alpha,beta) |
| Exponential(lambda) | lambda>0 | [0,inf) | 1/lambda | 1/lambda² | lambda=1/x_bar | Gamma(alpha,beta) |
| Gamma(alpha,beta) | alpha,beta>0 | [0,inf) | alpha/beta | alpha/beta² | method of moments | Gamma |
| Inverse-Gamma(alpha,beta) | alpha,beta>0 | (0,inf) | beta/(alpha-1) (a>1) | beta²/((a-1)²(a-2)) (a>2) | — | — |
| Beta(alpha,beta) | alpha,beta>0 | [0,1] | alpha/(alpha+beta) | alpha*beta/((a+b)²(a+b+1)) | method of moments | Beta |
| Dirichlet(alpha) | alpha_i>0 | K-simplex | alpha_i/alpha_0 | alpha_i(alpha_0-alpha_i)/(alpha_0²(alpha_0+1)) | — | — |
| Uniform(a,b) | a<b | [a,b] | (a+b)/2 | (b-a)²/12 | a=min(xi), b=max(xi) | Pareto |
| Lognormal(mu,sigma²) | mu in R, sigma²>0 | (0,inf) | exp(mu+sigma²/2) | (exp(sigma²)-1)*exp(2mu+sigma²) | mu=mean(log xi), sigma²=var(log xi) | Normal-Inv-Gamma |
| Weibull(k,lambda) | k,lambda>0 | [0,inf) | lambda*Gamma(1+1/k) | lambda²*(Gamma(1+2/k)-Gamma(1+1/k)²) | numerical | — |
| Pareto(alpha,xm) | alpha>0, xm>0 | [xm,inf) | alpha*xm/(alpha-1) (a>1) | xm²*alpha/((a-1)²(a-2)) (a>2) | alpha=n/sum(log xi/xm) | Gamma |
| Cauchy(x0,gamma) | x0 in R, gamma>0 | R | UNDEFINED | UNDEFINED | — | — |
| Beta-Binomial(n,alpha,beta) | n,alpha,beta>0 | {0,...,n} | n*alpha/(alpha+beta) | — | — | — |

**Critical LLM errors:** Cauchy has NO defined mean/variance. t distribution: mean=0 only for nu>1; variance=nu/(nu-2) only for nu>2.

## Inter-Distribution Relationships

```
Normal family:
  Z ~ N(0,1)
  Z1²+...+Zk² ~ Chi²(k)
  Z / sqrt(Chi²(k)/k) ~ t(k)
  (Chi²(d1)/d1) / (Chi²(d2)/d2) ~ F(d1,d2)
  exp(mu + sigma*Z) ~ Lognormal(mu,sigma²)

Exponential/Gamma family:
  Exponential(lambda) = Gamma(1, lambda)
  Gamma(n, lambda) = sum of n iid Exponential(lambda)  [n integer]
  Chi²(k) = Gamma(k/2, 1/2)
  Inverse-Gamma(alpha,beta) = 1/Gamma(alpha,beta)

Beta family:
  Uniform(0,1) = Beta(1,1)
  X~Gamma(a,theta), Y~Gamma(b,theta) => X/(X+Y) ~ Beta(a,b)
  Dirichlet is multivariate Beta

Limiting relationships:
  Binomial(n,p) -> Poisson(np) as n->inf, p->0, np=const
  Binomial(n,p) -> Normal(np, np(1-p)) as n->inf (CLT)
  Poisson(lambda) -> Normal(lambda,lambda) as lambda->inf
  t(nu) -> N(0,1) as nu->inf (rule of thumb: nu>30 normal approx OK)
  F(1,nu) = t(nu)²
```

## Maximum Likelihood Estimates (Closed Form)

| Distribution | MLE Parameters |
|-------------|----------------|
| Normal | mu_hat = x_bar; sigma²_hat = (1/n)*sum(xi-x_bar)² (biased; unbiased uses n-1) |
| Exponential | lambda_hat = 1/x_bar |
| Poisson | lambda_hat = x_bar |
| Binomial | p_hat = x_bar / n |
| Geometric | p_hat = 1 / x_bar |
| Pareto | alpha_hat = n / sum_i(log(xi/xm)); xm_hat = min(xi) |
| Uniform(a,b) | a_hat = min(xi); b_hat = max(xi) (biased; MLE is biased here) |
| Gamma(alpha,beta) | no closed form; use Newton's method on digamma equation |

## Moment Generating Functions (Key)

| Distribution | MGF M(t) | Valid for |
|-------------|----------|-----------|
| Normal(mu,sigma²) | exp(mu*t + sigma²t²/2) | all t |
| Exponential(lambda) | lambda/(lambda-t) | t < lambda |
| Binomial(n,p) | (1-p+p*e^t)^n | all t |
| Poisson(lambda) | exp(lambda*(e^t - 1)) | all t |
| Gamma(alpha,beta) | (beta/(beta-t))^alpha | t < beta |

**Source:** Casella & Berger "Statistical Inference" 2nd ed. (2002) + DeGroot & Schervish "Probability and Statistics" 4th ed.
