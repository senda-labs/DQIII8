# Knowledge Base — Quality Policy

## Why This Policy Exists

Knowledge chunks are injected into LLM prompts as authoritative context.
An incorrect chunk is worse than no chunk: it confidently misleads the model.
All numerical data must be traceable to a primary source.

---

## Data Categories

### A — Stable (no expiry)
Facts that do not change unless the underlying standard/definition changes:
- Mathematical formulas and algorithmic complexity (Big O)
- Physical constants, atomic masses, SI units
- Regulatory minimum thresholds published by standards bodies (Basel IV, NIST, IETF RFCs)
- Historical records with verifiable dates (Nobel winners, auction prices, biographical dates)
- Technical standards (HTTP status codes, TLS cipher suites, CVSS definitions)

**Action:** No temporal marker required. Cite the authoritative source once in the file footer.

### B — Temporal (expires)
Data that is accurate today but will change:
- Market rates: interest rates, P/E multiples, credit spreads, FX rates
- Benchmark performance: framework speeds, cloud latencies, hardware throughput
- Pricing: API costs, infrastructure pricing, SaaS multiples
- Macro parameters: GDP growth forecasts, inflation projections, unemployment rates
- Streaming/media statistics: MAU counts, royalty rates, box office totals

**Action:**
1. Add `last_verified: YYYY-MM` to file frontmatter
2. Add `⚠ Temporal: verify via [source] before use` header to the relevant section
3. Cite the source (URL or publication name) in the file's Quality Notes section

### C — Unverifiable (forbidden)
Data that cannot be traced to a primary source:
- Statistics like "73% of companies do X" without citing the survey/report
- Specific values without a source ("Tesla beta: 1.8")
- Subjective rankings presented as fact
- AI-generated "facts" that sound plausible but weren't verified

**Action:** Remove entirely. If the concept is useful, replace with the formula/structure
and leave the specific value blank or marked as `[verify: source]`.

---

## Rules for Adding New Chunks

1. **Every numerical value MUST have a cited source** (URL, publication name, or standard number)
2. **Temporal data MUST include `last_verified: YYYY-MM`** in frontmatter
3. **AI-generated chunks MUST be manually verified** before indexing
4. **Prefer formulas over values** — formulas don't expire, values do
5. **Each chunk MUST pass `has_specific_data()`** — if it fails, the data is too generic

---

## Preferred Verification Sources

| Domain | Source | URL |
|--------|--------|-----|
| Financial rates | Federal Reserve FRED | fred.stlouisfed.org |
| S&P 500 valuation | Damodaran (NYU) | stern.nyu.edu/~adamodar |
| Credit spreads | ICE BofA / FRED | fred.stlouisfed.org (BAML* series) |
| GDP/inflation | IMF World Economic Outlook | imf.org/en/Publications/WEO |
| Banking regulations | BIS / BCBS | bis.org/bcbs |
| Crypto standards | NIST | csrc.nist.gov/publications |
| TLS/network protocols | IETF RFCs | rfc-editor.org |
| Algorithm complexity | CLRS textbook | ISBN 978-0262046305 |
| DB/framework benchmarks | TechEmpower, TPC | techempower.com/benchmarks, tpc.org |
| Cloud latencies | Official vendor docs | docs.aws.amazon.com, cloud.google.com/docs |
| Art records | Christie's, Sotheby's, Grove Art | christies.com, sothebys.com |
| Film/music awards | AMPAS, Recording Academy | oscars.org, recordingacademy.com |
| Academic research | arXiv, Semantic Scholar | arxiv.org, semanticscholar.org |

---

## Knowledge Chunks Are NOT:
- Wikipedia copies (too broad, unreliable for specific values)
- AI-generated "facts" without verification
- Opinions or subjective rankings
- Marketing material from vendors (biased)
- Content that requires login to verify

---

## File Naming Convention

| Pattern | Content Type |
|---------|-------------|
| `*_reference.md` | Tables of stable reference values (Category A) |
| `*_parameters_YYYY.md` | Temporal parameters with year of verification |
| `*_benchmarks.md` | Performance data with Category B marking |
| `*_formulas.md` | Mathematical/financial formulas (Category A) |
| `paper_*.md` | Auto-ingested research papers (see papers/ subdirs) |

---

*Last policy update: 2026-03*
