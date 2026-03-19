# Skills Registry — INDEX

## Fuentes activas
- `cache/obsidian-skills/` → kepano/obsidian-skills (clonado 2026-03-12)
- `custom/` → skills aprobadas y listas para uso en producción

## Estado de revisión

| Skill | Fuente | Status | Aprobada por | Notas |
|-------|--------|--------|--------------|-------|
| obsidian-markdown | kepano/obsidian-skills | ✅ APROBADA | Iker | Sintaxis correcta para vault Obsidian — usar en todos los .md |
| obsidian-bases | kepano/obsidian-skills | ✅ APROBADA | Iker | Queries tipo SQL sobre notas Obsidian |
| defuddle | kepano/obsidian-skills | ✅ APROBADA | Iker | Extracción limpia de contenido web |
| obsidian-cli | kepano/obsidian-skills | ❌ RECHAZADA | Iker | Inútil en VPS sin interfaz gráfica |
| json-canvas | kepano/obsidian-skills | ⏸ APLAZADA | Iker | Canvas interactivo — aplazado para fase posterior |

## Regla de carga
Solo skills con estado ✅ APROBADA pueden añadirse a un combo.
Proceso: cache/ → revisión Iker → revisión Claude → APROBADA → custom/ → INDEX.

## Paths
- Cache: `skills-registry/cache/obsidian-skills/skills/`
- Custom (producción): `skills-registry/custom/`

## Rules integradas (ECC + DQIII8)

| Rule | Fuente | Status | Conflicto | Notas |
|------|--------|--------|-----------|-------|
| common/coding-style | ECC/affaan-m | ✅ APROBADA | No | Inmutabilidad, organización archivos |
| common/git-workflow | ECC/affaan-m | ✅ APROBADA (con override) | Leve | DQIII8 NOTE aplicado: atribución Co-Authored-By activa |
| common/agents | ECC/affaan-m | ✅ APROBADA (con override) | **Sí** | Override aplicado: agentes DQIII8 reemplazan tabla ECC |
| common/performance | ECC/affaan-m | ✅ APROBADA (con override) | **Sí** | Override aplicado: routing 3-tier DQIII8 reemplaza Haiku/Sonnet/Opus |
| common/security | ECC/affaan-m | ✅ APROBADA | No | Compatible con dqiii8-prohibitions |
| common/testing | ECC/affaan-m | ✅ APROBADA | No | 80% coverage, TDD |
| common/hooks | ECC/affaan-m | ✅ APROBADA | No | "no dangerously-skip-permissions" alineado con dqiii8-prohibitions |
| common/patterns | ECC/affaan-m | ✅ APROBADA | No | Repository pattern, skeleton projects |
| common/development-workflow | ECC/affaan-m | ✅ APROBADA | No | Research→Plan→TDD→Review→Commit |
| python/coding-style | ECC/affaan-m | ✅ APROBADA | No | PEP8, type hints — ver dqiii8-python para overrides |
| python/hooks | ECC/affaan-m | ✅ APROBADA | No | Black/ruff auto-format — compatible con PostToolUse DQIII8 |
| python/patterns | ECC/affaan-m | ✅ APROBADA | No | Protocol, dataclasses, async |
| python/security | ECC/affaan-m | ✅ APROBADA | No | dotenv, KeyError si falta secret |
| python/testing | ECC/affaan-m | ✅ APROBADA | No | pytest, coverage |
| dqiii8-prohibitions | DQIII8 | ✅ APROBADA | — | Reglas absolutas DQIII8, máxima prioridad |
| dqiii8-python | DQIII8 | ✅ APROBADA | — | Black, pathlib, encoding, async |
| dqiii8-autonomy | DQIII8 | ✅ APROBADA | — | Modo VPS, acciones destructivas |
| dqiii8-context-window | DQIII8 | ✅ APROBADA | — | Green/Yellow/Orange/Red thresholds |

## Revisión de agentes externos — VoltAgent/awesome-claude-code-subagents (2026-03-18)

Repositorio revisado: `VoltAgent/awesome-claude-code-subagents` (127+ agentes)
Fecha: 2026-03-18 | Revisado por: Iker + Claude

### Fase 1 — Agentes principales (research, data, creative)

| Agente DQIII8 | Candidato VoltAgent | Veredicto | Motivo |
|---------------|---------------------|-----------|--------|
| research-analyst | Sin equivalente (closest: technical-writer, content-marketer) | ✅ DQIII8 GANA | VoltAgent no tiene agente de síntesis de fuentes. technical-writer = docs, content-marketer = SEO/ROI. Ninguno hace research briefs. |
| data-analyst | data-analyst (haiku) + quant-analyst (opus) | ✅ DQIII8 GANA + ADOPCIÓN PARCIAL | data-analyst VoltAgent usa Haiku orientado a BI (Tableau/Power BI). quant-analyst (opus) es el agente correcto para trading sistemático con perfil financiero Carlos III. **Instalado**: quant-analyst como agente nuevo, no reemplazo de data-analyst. Separación de responsabilidades: data-analyst = WACC/DCF académico, quant-analyst = backtesting/VaR/GARCH/trading. |
| creative-writer | Sin equivalente (closest: content-marketer) | ✅ DQIII8 GANA | VoltAgent no tiene escritura narrativa creativa. content-marketer = SEO/conversiones/leads — opuesto a prosa literaria española xianxia. |

### Fase 2 — Agentes especializados para trading sistemático (2026-03-18)

| Agente VoltAgent | Categoría | Veredicto | Instalado |
|------------------|-----------|-----------|-----------|
| quant-analyst (opus) | 07-specialized-domains | ✅ INSTALADO | `.claude/agents/quant-analyst.md` |
| fintech-engineer (opus) | 07-specialized-domains | ✅ INSTALADO | `.claude/agents/fintech-engineer.md` — trading platform, exchange connectivity, order management |
| risk-manager (opus) | 07-specialized-domains | ✅ INSTALADO | `.claude/agents/risk-manager.md` — VaR, stress testing, Basel III, FRTB |
| competitive-analyst | — | ❌ NO EXISTE | No encontrado en ninguna categoría VoltAgent |
| K-Dense-AI/claude-scientific-skills | external | ⏸ APLAZADO | 170 skills de bioinformática/química — no relevante para trading. TimesFM (series temporales) genérico. Aplazado para si se abre proyecto científico. |
| quant-sentiment-ai/claude-equity-research | external | ⏸ PENDIENTE REVISIÓN | Goldman Sachs-style DCF + bull/bear/base scenarios. Instala vía plugin. Relevante para análisis fundamental de acciones. Aplazado para fase 2 trading-sistemático. |

## Skills auto-generadas desde git history (2026-03-12)

| Skill | Fuente | Status | Aprobada por | Notas |
|-------|--------|--------|--------------|-------|
| dqiii8-multi-provider-routing | git-analysis/dqiii8 (50 commits) | ✅ APROBADA | Iker | Patrón 3-tier routing: cuándo añadir providers, fallback chain, anti-patrones. Modelos Tier-2 corregidos (nemotron:free, qwen3:free) |
| dqiii8-agent-creation | git-analysis/dqiii8 (50 commits) | ✅ APROBADA | Iker | Estructura canónica de agentes, modelo correcto por tier, archivos co-cambiados. data-analyst corregido a claude-sonnet-4-6 |
| continuous-learning-v2 | ECC/affaan-m (adaptado) | ✅ APROBADA | Iker | Instincts SQLite + stop.py integration + /instinct-status command |

## Skills externas revisadas (2026-03-18)

| Skill | Fuente | Status | Aprobada por | Notas |
|-------|--------|--------|--------------|-------|
| vibesec | BehiSecc/VibeSec-Skill | ✅ APROBADA | Iker + Claude | OWASP top-10: SQL injection, SSRF, path traversal, secret exposure, file upload, XSS, CSRF, JWT, API security. Adaptada al stack Python/FastAPI/SQLite de DQIII8. Integrada en code-reviewer. |
| binance-spot | binance/binance-skills-hub | ✅ APROBADA | Iker + Claude | Binance Spot API completa: K-lines, order placement (MARKET/LIMIT/OCO/STOP), account info, trade history. Testnet + mainnet. Para proyecto trading-sistemático. |

## Combos activos (actualizado)

| Proyecto | Skills cargadas |
|----------|----------------|
| dqiii8-core | obsidian-markdown, obsidian-bases, evolved/ssim |
| content-automation | obsidian-markdown, fal-ai-media |
| hult-finance | obsidian-markdown, defuddle |
| leyendas-del-este | obsidian-markdown |
| trading-sistemático (futuro) | binance-spot + (pendiente: quant-sentiment-ai/claude-equity-research) |

> Nota: vibesec es skill del agente code-reviewer, no del proyecto. Se activa automáticamente en cada review.

## Agentes financieros/trading instalados (2026-03-18)

| Agente | Modelo | Path | Especialidad |
|--------|--------|------|--------------|
| quant-analyst | opus | `.claude/agents/quant-analyst.md` | Backtesting, Monte Carlo, VaR, GARCH, Black-Scholes, Sharpe, statistical arbitrage |
| fintech-engineer | opus | `.claude/agents/fintech-engineer.md` | Trading platform dev, exchange connectivity, order mgmt, KYC/AML, PCI DSS |
| risk-manager | opus | `.claude/agents/risk-manager.md` | VaR, stress testing, Basel III, FRTB, IFRS 9, market/credit/operational risk |
| data-analyst | claude-sonnet-4-6 | `.claude/agents/data-analyst.md` | WACC, DCF, valoración, modelos financieros académicos (Hult/Carlos III) |

> Separación: data-analyst = finanzas académicas/corporativas. quant-analyst + fintech-engineer + risk-manager = trading sistemático algorítmico.

## Skills P2a — ECC segunda revisión (2026-03-16)

| Skill | Fuente | Status | Aprobada por | Notas |
|-------|--------|--------|--------------|-------|
| security-review | ECC/affaan-m (adaptado Python/SQLite) | ✅ APROBADA | Iker | OWASP checklist DQIII8-adaptado: secrets, SQL injection, shell safety, hook safety |
| verification-loop | ECC/affaan-m (adaptado Black/pytest) | ✅ APROBADA | Iker | Pipeline post-código: black → ruff → mypy → pytest → security scan → diff |
| tdd-workflow | ECC/affaan-m (adaptado pytest) | ✅ APROBADA | Iker | TDD con pytest: RED→GREEN→REFACTOR, fixtures SQLite in-memory, smoke tests CLI |
| fal-ai-media | ECC/affaan-m (adaptado content-automation) | ✅ APROBADA | Iker | flux-general + negative_prompt + reference_image_url + Seedance video + costes |
| strategic-compact | ECC/affaan-m (adaptado DQIII8) | ✅ APROBADA | Iker | Compactar en boundaries lógicos, no mid-task; complementa dqiii8-context-window.md |
| evolved/ssim | /evolve auto (4 instincts) | ✅ APROBADA | Iker | R1-R4: delta-injection prohibida, resolucion scorer exacta, anomalia >0.1 = hacking, lever estructural |
