# Genetics Fundamentals

## Definition
Genetics is the study of genes, heredity, and genetic variation in living organisms. Genes are segments of DNA encoding instructions for building proteins. Genetics spans classical Mendelian inheritance, molecular mechanisms of gene expression, and modern genomics/CRISPR applications.

## Core Concepts

### DNA Structure and Replication
- **DNA double helix:** Two antiparallel strands of nucleotides (adenine-thymine, guanine-cytosine base pairs). Sugar-phosphate backbone. Sequence of bases encodes genetic information.
- **Replication:** Semi-conservative. DNA polymerase synthesizes new strands using each original strand as template. Requires primers (RNA). Error rate ~1 in 10^9 bases (after proofreading).
- **Chromosomes:** Compacted DNA + histone proteins. Humans have 46 chromosomes (23 pairs). Autosomes (1-22) + sex chromosomes (XX female, XY male).

### Gene Expression: Central Dogma
```
DNA → (transcription) → mRNA → (translation) → Protein
```
- **Transcription:** RNA polymerase reads the template strand 3'→5', synthesizes mRNA 5'→3'. Occurs in the nucleus. Pre-mRNA is processed: 5' cap, 3' poly-A tail, introns spliced out.
- **Translation:** Ribosome reads mRNA codons (3 nucleotides = 1 amino acid). tRNA anticodons carry amino acids. Start codon AUG (Met), three stop codons (UAA, UAG, UGA). Genetic code is nearly universal.
- **Gene regulation:** Transcription factors bind promoter regions to activate/repress genes. Enhancers and silencers act over long distances. Epigenetics: histone modification, DNA methylation alter gene expression without changing sequence.

### Mendelian Genetics
- **Alleles:** Alternative versions of a gene. Dominant (A) masks recessive (a) in heterozygotes.
- **Genotype vs. phenotype:** Genotype = allele combination (AA, Aa, aa). Phenotype = observable trait.
- **Punnett square:** Predicts offspring genotype probabilities from parental genotypes.
- **Law of Segregation:** Each parent passes one allele to offspring (gametes are haploid).
- **Law of Independent Assortment:** Genes on different chromosomes segregate independently. Exception: linked genes (on same chromosome) tend to be inherited together unless recombination occurs.
- **Incomplete dominance / Codominance:** Heterozygote has intermediate phenotype (incomplete) or expresses both alleles (codominance, e.g., ABO blood type).

### Mutations
- **Point mutations:** Single base changes. Silent (no AA change), missense (different AA), nonsense (premature stop codon).
- **Insertions/Deletions (indels):** Frameshift mutations disrupt reading frame downstream. Catastrophic if not in multiples of 3.
- **Copy number variants (CNVs):** Duplications or deletions of large DNA segments.
- **Mutation causes:** Replication errors, UV radiation (pyrimidine dimers), chemical mutagens, transposons.

### Genomics
- **Genome:** Complete set of DNA in an organism. Human genome: ~3 billion base pairs, ~20,000 protein-coding genes (only ~1.5% of genome). The rest: regulatory elements, introns, repetitive sequences, non-coding RNA.
- **SNPs (Single Nucleotide Polymorphisms):** Common single-base variations (~1 in 300 bases between individuals). Basis of GWAS (genome-wide association studies) linking variants to traits/diseases.
- **NGS (Next-Generation Sequencing):** High-throughput sequencing enabling whole-genome sequencing. Applications: cancer genomics, prenatal testing, pharmacogenomics, forensics.

### CRISPR-Cas9
```
Guide RNA (gRNA) directs Cas9 endonuclease to target DNA sequence → double-strand break
→ NHEJ (error-prone, gene knockout) or HDR (precise edit with repair template)
```
- **Applications:** Gene therapy (sickle cell disease, beta-thalassemia in clinical trials), functional genomics screens, agricultural improvement, diagnostics (SHERLOCK, DETECTR).
- **Limitations:** Off-target cuts, delivery to target tissue, immune response to Cas9. Base editing (no DSB) and prime editing reduce off-target risk.

### Hereditary Disease
- **Autosomal dominant:** One mutant allele sufficient (Huntington's, Marfan syndrome). Affected parent has 50% transmission risk.
- **Autosomal recessive:** Two mutant alleles required (cystic fibrosis, PKU, sickle cell). Carriers (Aa) are unaffected. 25% affected risk from two carrier parents.
- **X-linked:** Gene on X chromosome. Males (XY) are hemizygous — one copy. X-linked recessive affects males more (hemophilia A, Duchenne muscular dystrophy).
- **Polygenic/multifactorial:** Multiple genes + environment (diabetes type 2, hypertension, most psychiatric disorders). Heritability h² = genetic variance / total phenotypic variance.

## Key Values
- Human genome size: 3.2 × 10⁹ bp (haploid)
- Protein-coding genes: ~20,000
- Average gene size: ~27 kb (varies enormously)
- Codon degeneracy: 64 codons → 20 amino acids (multiple codons per AA)
