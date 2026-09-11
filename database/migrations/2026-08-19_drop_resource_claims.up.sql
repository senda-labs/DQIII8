-- Drop resource_claims: never had a production writer (grep confirms zero INSERTs
-- outside tests), so the multi-agent resource-lock feature it backed never
-- actually protected anything. The one reader, PermissionAnalyzer._check_resource_claim
-- (.claude/hooks/permission_analyzer.py), is removed in the same change so this
-- migration is safe to apply without triggering its fail-closed DENY path.
-- Human-applied only — see database/schema_v2.sql § agent write policy.
DROP INDEX IF EXISTS idx_resource_claims_expires;
DROP TABLE IF EXISTS resource_claims;
