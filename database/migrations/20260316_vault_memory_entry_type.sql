-- P2d: Add entry_type classification to vault_memory
-- entry_type priority in session_start.py: adr > project_state > lesson > checkpoint
ALTER TABLE vault_memory ADD COLUMN entry_type TEXT DEFAULT 'lesson'
    CHECK(entry_type IN ('adr','project_state','lesson','checkpoint'));
