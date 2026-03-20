# Hypothesis Testing Fundamentals

## Definition
Hypothesis testing is a statistical method for making decisions about population parameters using sample data. It provides a formal framework for determining whether observed data provides sufficient evidence to reject a null hypothesis in favor of an alternative.

## Core Concepts

- **Null Hypothesis (H0):** The default assumption — typically "no effect", "no difference", or "no relationship". Tests attempt to reject H0.
- **Alternative Hypothesis (H1/Ha):** What we suspect is true if H0 is false. One-tailed (directional) or two-tailed (any difference).
- **Test Statistic:** A number computed from sample data summarizing how far the data deviates from H0. Common examples: z-score, t-statistic, F-statistic, chi-square.
- **p-value:** Probability of observing data as extreme as the sample, assuming H0 is true. Small p-value = evidence against H0. NOT the probability that H0 is true.
- **Significance Level (alpha):** Threshold for rejection, typically 0.05 or 0.01. If p <= alpha, reject H0.
- **Type I Error (False Positive):** Rejecting H0 when it is actually true. Rate = alpha.
- **Type II Error (False Negative):** Failing to reject H0 when it is actually false. Rate = beta.
- **Statistical Power:** 1 - beta. Probability of correctly rejecting a false H0. Increases with sample size and effect size.
- **Confidence Intervals:** Range of plausible parameter values. A 95% CI means 95% of such intervals contain the true parameter.

## Common Tests
- **z-test:** Known population variance, large samples.
- **t-test:** Unknown variance. One-sample, two-sample, paired.
- **ANOVA:** Comparing means across 3+ groups.
- **Chi-square:** Categorical data, goodness-of-fit, independence.
- **Mann-Whitney / Wilcoxon:** Non-parametric alternatives when normality fails.

## Practical Applications
- **A/B testing:** "Does the new button color increase conversions?"
- **Clinical trials:** "Does the drug reduce blood pressure vs. placebo?"
- **Manufacturing:** "Is the production process within tolerance?"
- **Product analytics:** "Did this feature change retention?"
- **Research papers:** Reporting whether results are statistically significant.
