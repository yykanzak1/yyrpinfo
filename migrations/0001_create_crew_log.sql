CREATE TABLE IF NOT EXISTS crew_log (
  id TEXT PRIMARY KEY NOT NULL,
  activity TEXT NOT NULL CHECK(length(activity) BETWEEN 1 AND 80),
  result TEXT NOT NULL CHECK(result IN ('caught', 'not_caught')),
  cashed TEXT NOT NULL CHECK(cashed IN ('yes', 'no')),
  occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS crew_log_occurred_at_idx ON crew_log (occurred_at DESC);
