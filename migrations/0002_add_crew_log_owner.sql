ALTER TABLE crew_log ADD COLUMN created_by TEXT;
CREATE INDEX IF NOT EXISTS crew_log_created_by_idx ON crew_log (created_by);
