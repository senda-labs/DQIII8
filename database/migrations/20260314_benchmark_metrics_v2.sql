-- Benchmark metrics v2: advanced quality, cost, and time metrics
ALTER TABLE code_metrics ADD COLUMN prompt_length_tokens INTEGER;
ALTER TABLE code_metrics ADD COLUMN attempts_to_success INTEGER DEFAULT 1;
ALTER TABLE code_metrics ADD COLUMN first_attempt_success INTEGER DEFAULT 0;
ALTER TABLE code_metrics ADD COLUMN self_corrections INTEGER DEFAULT 0;
ALTER TABLE code_metrics ADD COLUMN syntax_errors INTEGER DEFAULT 0;
ALTER TABLE code_metrics ADD COLUMN import_errors INTEGER DEFAULT 0;
ALTER TABLE code_metrics ADD COLUMN constraint_violations INTEGER DEFAULT 0;
ALTER TABLE code_metrics ADD COLUMN ssim_delta_vs_prev REAL;
ALTER TABLE code_metrics ADD COLUMN color_palette_distance REAL;
ALTER TABLE code_metrics ADD COLUMN tokens_input INTEGER;
ALTER TABLE code_metrics ADD COLUMN tokens_output INTEGER;
ALTER TABLE code_metrics ADD COLUMN estimated_cost_usd REAL;
ALTER TABLE code_metrics ADD COLUMN wall_clock_seconds REAL;
ALTER TABLE code_metrics ADD COLUMN planning_seconds REAL;
ALTER TABLE code_metrics ADD COLUMN execution_seconds REAL;
ALTER TABLE code_metrics ADD COLUMN objective_clarity TEXT;
