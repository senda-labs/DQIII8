---
domain: formal_sciences
agent: stats-specialist
keywords_es: [test estadístico, normalidad, chi-cuadrado, ANOVA, no paramétrico, p-valor, hipótesis, Kruskal, Wilcoxon, Mann-Whitney, Shapiro, Levene]
keywords_en: [statistical test, normality, chi-square, ANOVA, nonparametric, p-value, hypothesis, Kruskal, Wilcoxon, Mann-Whitney, Shapiro, Levene]
---

# Statistical Tests — Decision Tree & Reference

## Decision Tree

```
DATA TYPE?
├── Categorical
│   ├── 2x2 table, n<1000 → Fisher's Exact Test
│   ├── RxC table → Chi-square (expected freq >= 5 per cell)
│   └── Goodness of fit → Chi-square (observed vs expected distribution)
│
└── Continuous/Ordinal
    ├── CHECK NORMALITY (Shapiro-Wilk if n<50; Kolmogorov-Smirnov if n>=50)
    │
    ├── NORMAL + equal variances (Levene's test p>0.05)
    │   ├── 1 sample vs known mean → One-sample t-test
    │   ├── 2 independent groups → Independent t-test (Student)
    │   ├── 2 paired groups → Paired t-test
    │   └── 3+ groups → One-way ANOVA → post-hoc Tukey HSD
    │
    ├── NORMAL + unequal variances
    │   ├── 2 groups → Welch's t-test (use by default, safer than Student)
    │   └── 3+ groups → Welch ANOVA → post-hoc Games-Howell
    │
    └── NON-NORMAL or ordinal
        ├── 2 independent groups → Mann-Whitney U (=Wilcoxon rank-sum)
        ├── 2 paired groups → Wilcoxon signed-rank test
        ├── 3+ independent groups → Kruskal-Wallis → post-hoc Dunn
        ├── 3+ paired groups → Friedman test → post-hoc Nemenyi
        └── Correlation
            ├── Both normal → Pearson r
            └── Non-normal / ordinal → Spearman rho or Kendall tau
```

## Test Reference Table (20 tests)

| Test | H₀ | Key Assumption | Statistic | df |
|------|-----|----------------|-----------|-----|
| One-sample t | mu = mu_0 | normality | t = (x_bar - mu_0)/(s/sqrt(n)) | n-1 |
| Independent t | mu_1 = mu_2 | normality, equal var | t = (x1-x2)/SE_pooled | n1+n2-2 |
| Welch's t | mu_1 = mu_2 | normality only | t = (x1-x2)/sqrt(s1²/n1+s2²/n2) | Welch-Satterthwaite |
| Paired t | mu_d = 0 | differences normal | t = d_bar/(s_d/sqrt(n)) | n-1 |
| One-way ANOVA | all mu_i equal | normality, equal var | F = MS_between/MS_within | k-1, n-k |
| Welch ANOVA | all mu_i equal | normality only | F_Welch | adjusted |
| Two-way ANOVA | no main/interaction effects | normality, equal var | F for each factor | — |
| Chi-square GoF | observed = expected | expected >= 5 | chi² = sum((O-E)²/E) | k-1 |
| Chi-square indep | variables independent | expected >= 5 | chi² = sum((O-E)²/E) | (r-1)(c-1) |
| Fisher's Exact | OR = 1 | 2x2 table, small n | hypergeometric exact | — |
| Mann-Whitney U | distributions equal | continuous | U = n1*n2 + n1(n1+1)/2 - R1 | — |
| Wilcoxon signed | median diff = 0 | symmetric differences | W = sum of signed ranks | — |
| Kruskal-Wallis | all medians equal | independent samples | H = 12/(N(N+1)) * sum(Ri²/ni) - 3(N+1) | k-1 |
| Friedman | no row/column effects | blocked design | Q = 12/(bk(k+1)) * sum(Rj²) - 3b(k+1) | k-1 |
| Pearson r | rho = 0 | bivariate normal | t = r*sqrt(n-2)/sqrt(1-r²) | n-2 |
| Spearman rho | rho_s = 0 | monotonic relationship | same as Pearson on ranks | n-2 |
| Shapiro-Wilk | sample is normal | n<=2000 (best n<50) | W statistic | — |
| Levene's | variances equal | — | F on absolute deviations from mean | k-1, n-k |
| Bartlett's | variances equal | normality required | chi² | k-1 |
| Kolmogorov-Smirnov | follows distribution | continuous distribution | D = max|F_n(x)-F(x)| | — |

## ASA 2016 P-value Statement — 6 Principles

1. P-values can indicate incompatibility of data with a specified statistical model.
2. P-values do NOT measure probability that the null hypothesis is true.
3. Scientific conclusions should NOT be based only on whether p crosses a threshold.
4. Proper inference requires full reporting and transparency (not cherry-picking).
5. P-value does NOT measure size of an effect or importance of a result.
6. A p-value alone does NOT provide a good measure of evidence regarding a model or hypothesis.

**Source:** Wasserstein & Lazar (2016), "The ASA's Statement on p-Values" — doi:10.1080/00031305.2016.1154108

## Multiple Comparisons Corrections

| Method | Formula | When to Use |
|--------|---------|-------------|
| Bonferroni | alpha_adj = alpha/m | conservative, any dependency structure |
| Holm-Bonferroni | step-down Bonferroni | more powerful than Bonferroni, same control |
| Benjamini-Hochberg | controls FDR = E[V/R] | exploratory, many tests (genomics) |
| Tukey HSD | q distribution | only for ANOVA pairwise comparisons |
| Sidak | alpha_adj = 1-(1-alpha)^(1/m) | independent tests only |

## Effect Size Reference

| Test | Measure | Small | Medium | Large |
|------|---------|-------|--------|-------|
| t-test | Cohen's d = (mu1-mu2)/sigma_pooled | 0.2 | 0.5 | 0.8 |
| ANOVA | eta² = SS_between/SS_total | 0.01 | 0.06 | 0.14 |
| ANOVA | omega² (less biased than eta²) | 0.01 | 0.06 | 0.14 |
| Correlation | r | 0.1 | 0.3 | 0.5 |
| Chi-square (2x2) | phi = sqrt(chi²/n) | 0.1 | 0.3 | 0.5 |
| Chi-square (RxC) | Cramer's V = sqrt(chi²/(n*min(r-1,c-1))) | 0.1 | 0.3 | 0.5 |
| Mann-Whitney | rank-biserial r = 1-2U/(n1*n2) | 0.1 | 0.3 | 0.5 |

**Source:** ASA Statement on P-Values (2016) + Sheskin "Handbook of Parametric and Nonparametric Statistical Procedures" 5th ed.
