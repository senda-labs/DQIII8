-- Stage 8.1/8.3 (ROI/Tiempos/Costes/Performance addendum, see
-- /root/.claude/plans/distributed-wobbling-gem.md): new tables for project revenue,
-- budget targets, real infra costs, and the labor rate used to price human hours.

CREATE TABLE IF NOT EXISTS project_value (
  id INTEGER PRIMARY KEY,
  project TEXT NOT NULL,
  fecha TEXT NOT NULL DEFAULT (datetime('now')),
  tipo TEXT NOT NULL CHECK (tipo IN ('fee_cobrado','hito_entregado','valor_estimado')),
  importe_eur REAL NOT NULL,
  nota TEXT
);

CREATE INDEX IF NOT EXISTS idx_project_value_project ON project_value(project, fecha);

CREATE TABLE IF NOT EXISTS project_budget (
  project TEXT PRIMARY KEY,
  presupuesto_eur REAL NOT NULL,
  updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS infra_costs (
  id INTEGER PRIMARY KEY,
  item TEXT NOT NULL,
  importe_eur_mes REAL NOT NULL,
  activo_desde TEXT NOT NULL DEFAULT (date('now')),
  activo_hasta TEXT,
  nota TEXT
);

CREATE TABLE IF NOT EXISTS labor_rates (
  id INTEGER PRIMARY KEY,
  rate_eur_hour REAL NOT NULL,
  basis TEXT,
  effective_date TEXT NOT NULL DEFAULT (date('now'))
);

-- Real infra_costs/labor_rates seed rows are deliberately NOT tracked here:
-- this repo is public, and the actual monthly figures + rate-derivation
-- basis are operator-specific business data. They were applied directly to
-- the live DB out-of-band (git-ignored, like database/dqiii8.db itself).
-- To seed a fresh install:
--   sqlite3 database/dqiii8.db "INSERT INTO infra_costs (item, importe_eur_mes, nota) VALUES ('<item>', <eur_per_month>, '<note>');"
--   python3 bin/tools/project_ctl.py rate set <eur_per_hour> --basis "<derivation basis>"

INSERT INTO schema_migrations (version, applied_at)
VALUES ('2026-08-13_project_value_and_budget', datetime('now'));
