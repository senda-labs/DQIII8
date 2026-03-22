---
domain: natural_sciences
agent: biology-specialist
keywords_es: [glucólisis, Krebs, fosforilación oxidativa, enzima, ATP, NAD, FADH2, regulación, hexoquinasa, piruvato quinasa, ETC, complejo mitocondrial]
keywords_en: [glycolysis, Krebs, oxidative phosphorylation, enzyme, ATP, NAD, FADH2, regulation, hexokinase, pyruvate kinase, ETC, mitochondrial complex]
---

# Metabolic Pathways — Enzymes, Energetics & Regulation

## Glycolysis (10 Steps)

| Step | Substrate → Product | Enzyme | Type | ΔG°' (kJ/mol) | Regulated? |
|------|---------------------|--------|------|--------------|------------|
| 1 | Glucose → G6P | Hexokinase / Glucokinase | phosphorylation (ATP) | −16.7 | YES — inhibited by G6P (HK); glucokinase NOT inhibited (liver) |
| 2 | G6P → F6P | Phosphoglucose isomerase | isomerization | +1.7 | no |
| 3 | F6P → F1,6BP | Phosphofructokinase-1 (PFK-1) | phosphorylation (ATP) | −14.2 | YES — major checkpoint: +AMP, +F2,6BP; −ATP, −citrate |
| 4 | F1,6BP → DHAP + G3P | Aldolase | aldol cleavage | +23.8 | no |
| 5 | DHAP → G3P | Triosephosphate isomerase | isomerization | +7.5 | no (near equilibrium) |
| 6 | G3P → 1,3-BPG | Glyceraldehyde-3-P dehydrogenase | oxidation + phosphorylation | −6.3 | no; inhibited by arsenate |
| 7 | 1,3-BPG → 3PG | Phosphoglycerate kinase | substrate-level phosphorylation | −18.8 | no; first ATP synthesis |
| 8 | 3PG → 2PG | Phosphoglycerate mutase | isomerization | +4.4 | no |
| 9 | 2PG → PEP + H₂O | Enolase | dehydration | +1.8 | inhibited by F |
| 10 | PEP → Pyruvate | Pyruvate kinase | substrate-level phosphorylation | −31.4 | YES — +F1,6BP (feedforward); −ATP, −alanine (liver: −glucagon) |

**Net glycolysis:** Glucose + 2NAD⁺ + 2ADP + 2Pᵢ → 2 Pyruvate + 2NADH + 2ATP + 2H₂O + 2H⁺

**Irreversible steps (thermodynamically, committed):** Steps 1, 3, 10 — these are bypassed in gluconeogenesis.

## Pyruvate Dehydrogenase Complex (PDC)

Pyruvate → Acetyl-CoA + CO₂ + NADH | ΔG°' = −33.4 kJ/mol

Activated by: CoA, NAD⁺, ADP, Ca²⁺
Inhibited by: Acetyl-CoA, NADH, ATP, fatty acids (via PDK)
Three enzymes: E1 (pyruvate decarboxylase, TPP), E2 (dihydrolipoyl transacetylase), E3 (dihydrolipoyl dehydrogenase, FAD)

## Krebs Cycle / TCA Cycle (8 Steps)

| Step | Substrate → Product | Enzyme | Cofactors | ΔG°' (kJ/mol) | CO₂ |
|------|---------------------|--------|-----------|--------------|-----|
| 1 | Oxaloacetate + Acetyl-CoA → Citrate | Citrate synthase | — | −31.4 | no |
| 2 | Citrate → Isocitrate | Aconitase | Fe-S | +6.3 | no |
| 3 | Isocitrate → α-KG + CO₂ | Isocitrate dehydrogenase | NAD⁺ | −20.9 | YES |
| 4 | α-KG → Succinyl-CoA + CO₂ | α-KG dehydrogenase complex | NAD⁺, CoA, TPP | −33.5 | YES |
| 5 | Succinyl-CoA → Succinate | Succinyl-CoA synthetase | GDP/ADP | −2.9 | no |
| 6 | Succinate → Fumarate | Succinate dehydrogenase (Complex II) | FAD | +0 | no |
| 7 | Fumarate → Malate | Fumarase | H₂O | −3.8 | no |
| 8 | Malate → Oxaloacetate | Malate dehydrogenase | NAD⁺ | +29.7 | no |

**Net per Acetyl-CoA:** 3NADH + FADH₂ + GTP + 2CO₂

Regulation: Step 3 (IDH): +ADP, +Ca²⁺; −NADH, −ATP | Step 4 (α-KGDH): +Ca²⁺; −NADH, −succinyl-CoA

## Electron Transport Chain (ETC)

| Complex | Common Name | Reaction | H⁺ pumped/2e⁻ | Classic Inhibitor | Site |
|---------|------------|---------|----------------|------------------|------|
| CI | NADH dehydrogenase | NADH + Q → NAD⁺ + QH₂ | 4 H⁺ | Rotenone, Amytal | IM |
| CII | Succinate dehydrogenase | Succinate + Q → Fumarate + QH₂ | 0 H⁺ | Malonate (competitive), carboxin | IM |
| CIII | Cytochrome bc1 complex | QH₂ + 2cyt_c(ox) → Q + 2cyt_c(red) | 4 H⁺ (Q cycle) | Antimycin A, myxothiazol | IM |
| CIV | Cytochrome c oxidase | 4cyt_c(red) + O₂ → 4cyt_c(ox) + 2H₂O | 2 H⁺ | Cyanide, CO, azide, H₂S | IM |
| CV | ATP synthase (F₀F₁) | ADP + Pᵢ → ATP | consumes 4 H⁺/ATP | Oligomycin (F₀), DCCD | IM |

**P/O ratios (corrected, 2002+):**
- NADH: 2.5 ATP (NOT 3 as in old textbooks)
- FADH₂: 1.5 ATP (NOT 2)

**Total ATP per glucose (current consensus):** ~30–32 ATP
- Glycolysis: 2 ATP + 2 NADH_cytoplasm
- PDC: 2 NADH_mito
- TCA: 6 NADH + 2 FADH₂ + 2 GTP
- Malate-aspartate shuttle (NADH_cyto → mito): +2.5 per NADH
- Glycerol-3-phosphate shuttle: +1.5 per NADH_cyto

**DO NOT use 36-38 ATP** — that number is obsolete (based on P/O=3 and 2 respectively).

## Gluconeogenesis Bypass Enzymes (irreversible steps reversed)

| Glycolysis step bypassed | Gluconeogenesis enzyme | Location |
|-------------------------|----------------------|----------|
| PK (step 10) | PEPCK (oxaloacetate → PEP) | mito + cytoplasm |
| PFK-1 (step 3) | Fructose-1,6-bisphosphatase (F1,6BPase) | cytoplasm |
| HK/GK (step 1) | Glucose-6-phosphatase | ER lumen (liver, kidney only) |

**Source:** KEGG Pathway Database (kegg.jp) + Lehninger "Principles of Biochemistry" 8th ed. (2021) + Nelson & Cox
