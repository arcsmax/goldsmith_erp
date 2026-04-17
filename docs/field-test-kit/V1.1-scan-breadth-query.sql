-- V1.1 secondary success metric — scan-breadth % (Lena §6 killer #3 / A13.2)
--
-- Rationale: `switch_timer` creates a new `time_entries` row per scan.
-- A goldsmith who heavy-scans (20x/day) creates 20 'scan' rows; another
-- who starts once manually and stays on one entry creates 1 'manual'
-- row. The primary ratio metric drifts with scan-style rather than
-- true adoption.
--
-- The breadth metric answers: "what fraction of GOLDSMITH users
-- actually used the scanner at least once in the last 7 days?". It is
-- a user-count ratio, not a row-count ratio, so it is immune to the
-- per-user-volume skew.
--
-- Rules baked in:
--   - Scope to GOLDSMITH, excluding test users (same as primary metric).
--   - Exclude correction entries.
--   - 7-day window (Lena §6 recommendation; matches ship-day calendar
--     dashboard view in SHIP-DAY-CALENDAR Part C row a).
--
-- Interpretation:
--   - Use this as a secondary indicator alongside the primary adoption
--     ratio. If primary is volatile week-to-week but breadth is stable
--     and > 80%, the scan tool is in routine use and the primary ratio
--     is picking up workflow noise.
--   - Low breadth (<= 50%) with high primary ratio indicates a single
--     power-user carrying the numbers; the feature is not broadly
--     adopted. Not a stop-ship trigger — a UX investigation trigger.

SELECT
  COUNT(DISTINCT CASE WHEN te.origin = 'scan' THEN te.user_id END) * 100.0
    / NULLIF(COUNT(DISTINCT te.user_id), 0)
    AS scan_breadth_pct
FROM time_entries te
JOIN users u ON u.id = te.user_id
WHERE te.created_at > now() - interval '7 days'
  AND u.role = 'GOLDSMITH'
  AND u.is_test_user = FALSE
  AND te.correction_of IS NULL;
