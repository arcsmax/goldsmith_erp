-- V1.1 primary success metric — scan-adoption % (spec §14.a row a)
--
-- Amendment A13.1 / TESTABILITY-REVIEW §1. Replaces the naive query that
-- shipped in the original Slice 13 plan. The naive version divided by
-- COUNT(*) which inflates the denominator with 'import', 'recovery',
-- admin diagnostic and test-user rows.
--
-- Rules baked in:
--   - Scope to GOLDSMITH-role users only. Admin diagnostics and VIEWER
--     reads do not belong in the adoption ratio.
--   - Exclude users flagged `is_test_user = TRUE` (Slice 2 / A2.1).
--   - Exclude correction entries (`correction_of IS NOT NULL`, Slice 2 /
--     A2.2) so that payroll fixups do not double-count the base event.
--   - Denominator restricted to origin IN ('scan','manual') — 'import'
--     and 'recovery' rows neither started via a user action today.
--   - 30-day rolling window (spec §14.a gate cadence).
--   - NULLIF guards against divide-by-zero on empty windows.
--
-- Gate thresholds (spec §14.a):
--   >= 60.0  → adoption target met; proceed to V1.1.5 planning.
--   30..60   → yellow. Investigate top drop-off (usually camera-denied
--              fallback too slow, or HID default-off onboarding).
--   < 30.0   → stop-ship trigger. Halt V1.1.5 planning per spec §14.a
--              second-round threshold.
--
-- This file is executable against the production database. Meant for
-- `make shell-db` copy-paste and for the `/admin/scan-metrics` endpoint.

SELECT
  COUNT(*) FILTER (WHERE te.origin = 'scan') * 100.0
    / NULLIF(COUNT(*) FILTER (WHERE te.origin IN ('scan','manual')), 0)
    AS scan_adoption_pct
FROM time_entries te
JOIN users u ON u.id = te.user_id
WHERE te.created_at > now() - interval '30 days'
  AND u.role = 'GOLDSMITH'
  AND u.is_test_user = FALSE
  AND te.correction_of IS NULL;
