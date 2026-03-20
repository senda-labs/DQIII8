# BMR & TDEE Calculations

## Basal Metabolic Rate (BMR) Equations

### Mifflin-St Jeor (preferred by Academy of Nutrition and Dietetics)
```
Male:   BMR = 10×W + 6.25×H - 5×A + 5
Female: BMR = 10×W + 6.25×H - 5×A - 161
```
- W: weight (kg), H: height (cm), A: age (years)
- Most accurate for general population (±10%)

### Harris-Benedict (revised 1984, Roza & Shizgal)
```
Male:   BMR = 88.362 + 13.397×W + 4.799×H - 5.677×A
Female: BMR = 447.593 + 9.247×W + 3.098×H - 4.330×A
```
Tends to overestimate by ~5% vs. Mifflin.

### Katch-McArdle (requires body fat %)
```
BMR = 370 + 21.6 × LBM
LBM = W × (1 - BF%)
```
- LBM: Lean Body Mass (kg)
- Most accurate when body composition is known
- Use when BF% differs significantly from average (athletes, obese)

## TDEE Activity Multipliers
| Level | Description | Multiplier |
|-------|-------------|------------|
| Sedentary | Office job, no exercise | 1.200 |
| Light | Exercise 1-2x/week | 1.375 |
| Moderate | Exercise 3-5x/week | 1.550 |
| Active | Exercise 6-7x/week | 1.725 |
| Very active | 2x/day or physical job | 1.900 |

```
TDEE = BMR × Activity Multiplier
```

## NEAT Estimation
```
NEAT calories ≈ steps/day × 0.04 kcal/step
```
- 5,000 steps → ~200 kcal/day NEAT
- 10,000 steps → ~400 kcal/day NEAT
- Increases TDEE beyond the multiplier table above

## Accuracy Notes
- All equations are population averages; individual variance ±15%
- Recalculate BMR/TDEE every 5-10 kg weight change
- Mifflin preferred for overweight populations; Katch-McArdle for athletes
