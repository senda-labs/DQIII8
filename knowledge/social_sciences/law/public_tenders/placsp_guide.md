# PLACSP Guide — Plataforma de Contratación del Sector Público

## Overview
URL: https://contrataciondelestado.es
Official national procurement platform (mandatory for AGE; voluntary but widely adopted by CCAA/local).
LCSP art. 347: all contract notices must be published in PLACSP (or equivalent regional platform).
Regional platforms: VORTAL (Cataluña/ContraCC), JCCM (Castilla-La Mancha), etc. — all feed into PLACSP.

## Search and Filtering

### Key Search Fields
- **CPV Code (Código CPV)**: EU Common Procurement Vocabulary — 8-digit code identifying contract object
  - Works: Division 45 (e.g., 45231000 — pipeline works)
  - IT services: 72000000–72920000
  - Consulting: 73000000–73436000
  - Cleaning: 90910000
- **Contracting body (Órgano de contratación)**: filter by specific ministry, municipality, public entity
- **Contract type**: obras, servicios, suministros, concesión, etc.
- **Procedure type**: abierto, restringido, negociado, diálogo competitivo
- **Estimated value range**: min/max VEC in euros
- **Publication date**: range filter
- **Status**: published, deadline today, awarded, cancelled

### Alert Setup (Alertas de licitaciones)
1. Register/login at contrataciondelestado.es
2. Go to "Mis Alertas" → Nueva Alerta
3. Set: CPV codes, contracting body, value range, procedure type
4. Frequency: daily email digest of new publications matching criteria
5. Critical: check both PLACSP and regional platform for your target market

## DEUC — Documento Europeo Único de Contratación

### What it is
Self-declaration form replacing all solvency and qualification documents at initial stage.
Full evidence only required from winning tenderer (or when specifically requested).
Reduces administrative burden for tenderers.

### DEUC Structure
- Part I: Information about the procurement procedure
- Part II: Information concerning the economic operator
  - Identity, legal form, registration numbers (NIF, CNAE, NACE)
  - Representation and participation (subcontracting, consortiums — UTE)
- Part III: Exclusion grounds (prohibition to contract — art. 71 LCSP)
  - Criminal convictions (corruption, fraud, money laundering)
  - Tax/social security debts (certificados de estar al corriente)
  - Insolvency, liquidation proceedings
- Part IV: Selection criteria (solvency self-declaration)
  - Economic/financial criteria
  - Technical/professional criteria
- Part V: Reduction of candidates (restricted procedure)
- Part VI: Concluding statements + signature

### DEUC Digital Tool
- EU espd-service: https://espd.ted.europa.eu
- Generate XML → upload to PLACSP tender
- Download pre-filled XML from tender notice → complete → re-upload

## Electronic Submission Requirements

### Digital Signature
- Certificado electrónico recognized: DNIe, certificado de representante de persona jurídica, certificado de empleado público
- Issued by: FNMT-RCM (Fábrica Nacional de Moneda y Timbre), Camerfirma, ACCV, ANF AC
- Qualified electronic signature = handwritten signature equivalent (eIDAS Regulation)

### Technical Requirements
- Browser: Chrome, Firefox, Edge (IE not supported post-2023)
- Java: Not required in modern PLACSP (legacy tenders may still need it)
- File formats accepted: PDF, XML, ZIP (check specific tender — some accept Office formats)
- File size: typically ≤ 300MB per envelope; large files may require external link

### Submission Process
1. Download pliego (PCAP + PPT) from PLACSP tender page
2. Prepare documents for each sobre (A, B, C)
3. Create encrypted/protected packages if required by pliego
4. Access "Presentar Oferta" button (only active during submission window)
5. Upload each sobre separately
6. Obtain submission receipt (justificante de presentación) — mandatory evidence of timely submission
7. Store receipt: proves submission timestamp in case of disputes

## Key Dates in PLACSP Tender Notice
| Field | Meaning |
|-------|---------|
| Fecha límite presentación | Submission deadline (hard cutoff — system closes automatically) |
| Fecha apertura sobre A | Date administrative envelopes opened (often same day or next day) |
| Fecha apertura sobre B | Technical opening (announced after admin qualification) |
| Fecha apertura sobre C | Economic opening (announced after B scoring) |

## After Award — Key Documents in PLACSP
- Resolución de adjudicación: published within 15 days of award decision
- Anuncio de formalización: published after contract signed (within 15 days)
- Modificaciones contractuales: all modifications >20% VEC must be published
- Actas de la Mesa de Contratación: increasingly published (transparency requirement)

## Consortium (UTE — Unión Temporal de Empresas)
```
UTE requirements:
- Commitment to form UTE if awarded (comprometerse a constituirse)
- Indicate % participation of each member
- All members sign the offer jointly
- Solvency: can be pooled across members
- Constitution: formal UTE deed (escritura) required before contract signing
- Tax regime: transparent entity; members declare proportional profits
```
