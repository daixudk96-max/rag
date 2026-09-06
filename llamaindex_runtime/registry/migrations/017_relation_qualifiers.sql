-- Phase 14 explicit relation qualifiers with JSONB spillover.

ALTER TABLE relations ADD COLUMN IF NOT EXISTS negation BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE relations ADD COLUMN IF NOT EXISTS condition TEXT;
ALTER TABLE relations ADD COLUMN IF NOT EXISTS direction TEXT;
ALTER TABLE relations ADD COLUMN IF NOT EXISTS confidence NUMERIC;
ALTER TABLE relations ADD COLUMN IF NOT EXISTS qualifiers JSONB;
