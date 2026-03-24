# Diet Plan Generator Template

## Required Inputs
- Height (cm), Weight (kg), Age (years), Sex (M/F)
- Body fat % (optional, enables Katch-McArdle)
- Activity level (sedentary / light / moderate / active / very active)
- Goal: fat loss / muscle gain / recomposition / maintenance
- Allergies / intolerances (dairy, gluten, nuts, shellfish, etc.)
- Budget tier: budget / moderate / premium
- Meal count preference: 3 / 4 / 5 meals/day

## Calculation Pipeline

### Step 1 — BMR
```
If BF% known:
  LBM = weight × (1 - BF%)
  BMR = 370 + 21.6 × LBM  [Katch-McArdle]
Else:
  Male:   BMR = 10W + 6.25H - 5A + 5
  Female: BMR = 10W + 6.25H - 5A - 161  [Mifflin-St Jeor]
```

### Step 2 — TDEE
```
TDEE = BMR × activity_multiplier
(1.2 / 1.375 / 1.55 / 1.725 / 1.9)
```

### Step 3 — Target Calories
```
Fat loss:      TDEE - 400 kcal
Muscle gain:   TDEE + 300 kcal
Recomposition: TDEE (no adjustment)
Maintenance:   TDEE
```

### Step 4 — Macro Split
```
Protein = goal_specific_g/kg × weight  [see macronutrient_targets.md]
Protein_kcal = protein_g × 4
Fat_kcal = target_calories × 0.28  (28% default)
Fat_g = fat_kcal / 9
Carb_kcal = target_calories - protein_kcal - fat_kcal
Carb_g = carb_kcal / 4
```

### Step 5 — Meal Distribution
```
Protein per meal = total_protein / meal_count
  (cap at 40g per meal — add meal if needed)
Pre-workout meal: +30% carbs vs average
Post-workout meal: 20-40g protein + 1g/kg carbs
```

### Step 6 — Food Selection
- Filter by allergies/intolerances
- Select from budget-appropriate sources
- Assign minimum 3 different protein sources per week

## Worked Example: 28M, 182cm, 78.65kg, Active, Recomposition

```
BMR  = 10(78.65) + 6.25(182) - 5(28) + 5
     = 786.5 + 1137.5 - 140 + 5 = 1789 kcal

TDEE = 1789 × 1.725 = 3086 kcal
Target = 3086 kcal (recomposition = maintenance)

Protein = 2.0 × 78.65 = 157g → 628 kcal
Fat     = 3086 × 0.28 = 864 kcal → 96g
Carbs   = 3086 - 628 - 864 = 1594 kcal → 399g

4 meals × ~39g protein each
```

## Output Format
```
=== PERSONALIZED PLAN ===
Target calories: X kcal/day
Macros: Xg protein | Xg fat | Xg carbs
Meal 1 (breakfast): ...
Meal 2 (lunch): ...
Meal 3 (pre-workout): ...
Meal 4 (post-workout/dinner): ...
Hydration: X liters/day
Key supplements (if gaps): ...
Weekly rotation: Week A / Week B menus
```

## Constraints / When Not to Use
- Medical conditions (diabetes, CKD, eating disorders) → refer to dietitian
- Pregnancy/lactation → different RDA values apply
- Under 18 → different caloric/protein needs
- BMI < 18 or > 40 → clinical supervision recommended
