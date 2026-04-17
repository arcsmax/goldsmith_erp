/**
 * V1.1 Slice 13 — Scan-adoption dashboard (ADMIN only).
 *
 * Renders the six §14.a tiles Kai listed in SHIP-DAY-CALENDAR Part C.
 * Mount at `/admin/scan-gate`. The endpoint behind this page lives at
 * GET /api/v1/admin/scan-metrics (see admin_scan_metrics.py).
 *
 * Deliberate V1.1 choices:
 *   - Styling is minimal. Refinement is explicitly V1.2 scope per the
 *     slice instructions ("shipping functional, not pretty").
 *   - No live-update / WebSocket. The data changes slowly (30 d rolling
 *     window) and a manual refresh button is enough for the gate-readout
 *     cadence (weekly, then day-30 final).
 *   - Bundle-size (row f) is NOT rendered here — it lives in CI output
 *     and docs/field-test-kit/bundle-trend.csv. We render a link
 *     instead, keeping the backend endpoint responsible only for data
 *     it can actually query.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { getScanMetrics, ScanMetrics } from '../../api/admin';

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function formatPct(n: number | null): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return `${n.toFixed(1)}%`;
}

function formatMs(n: number | null): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  if (n >= 1000) return `${(n / 1000).toFixed(2)} s`;
  return `${Math.round(n)} ms`;
}

function formatCount(n: number): string {
  return n.toLocaleString('de-DE');
}

// Gate thresholds (spec §14.a)
const ADOPTION_TARGET = 60;
const ADOPTION_HALT = 30;
const LATENCY_TARGET_MS = 5000;
const LATENCY_STOP_SHIP_MS = 10000;

function adoptionStatus(pct: number | null): 'ok' | 'yellow' | 'halt' | 'na' {
  if (pct === null) return 'na';
  if (pct >= ADOPTION_TARGET) return 'ok';
  if (pct < ADOPTION_HALT) return 'halt';
  return 'yellow';
}

function latencyStatus(p95: number | null): 'ok' | 'yellow' | 'halt' | 'na' {
  if (p95 === null) return 'na';
  if (p95 > LATENCY_STOP_SHIP_MS) return 'halt';
  if (p95 > LATENCY_TARGET_MS) return 'yellow';
  return 'ok';
}

// ---------------------------------------------------------------------------
// Small components (no external design system — functional only)
// ---------------------------------------------------------------------------

const tileBaseStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: '0.4rem',
  padding: '1.25rem 1.5rem',
  background: '#ffffff',
  border: '1px solid #d4d4d8',
  borderRadius: '0.5rem',
  minHeight: '140px',
  boxShadow: '0 1px 2px rgba(0, 0, 0, 0.04)',
};

const statusColors: Record<'ok' | 'yellow' | 'halt' | 'na', string> = {
  ok: '#22c55e',
  yellow: '#eab308',
  halt: '#ef4444',
  na: '#9ca3af',
};

interface TileProps {
  title: string;
  subtitle: string;
  value: string;
  status?: 'ok' | 'yellow' | 'halt' | 'na';
  footnote?: string;
}

const Tile: React.FC<TileProps> = ({ title, subtitle, value, status = 'na', footnote }) => (
  <div style={tileBaseStyle}>
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
      <span
        aria-hidden
        style={{
          display: 'inline-block',
          width: '10px',
          height: '10px',
          borderRadius: '50%',
          background: statusColors[status],
        }}
      />
      <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#52525b' }}>
        {title}
      </span>
    </div>
    <span style={{ fontSize: '2rem', fontWeight: 700, color: '#18181b', lineHeight: 1.1 }}>
      {value}
    </span>
    <span style={{ fontSize: '0.78rem', color: '#71717a' }}>{subtitle}</span>
    {footnote ? (
      <span style={{ fontSize: '0.72rem', color: '#9ca3af', marginTop: 'auto' }}>
        {footnote}
      </span>
    ) : null}
  </div>
);

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export const ScanAdoptionDashboard: React.FC = () => {
  const [metrics, setMetrics] = useState<ScanMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastLoadedAt, setLastLoadedAt] = useState<Date | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getScanMetrics();
      setMetrics(data);
      setLastLoadedAt(new Date());
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Unbekannter Fehler';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div style={{ padding: '1.5rem', maxWidth: '1200px', margin: '0 auto' }}>
      <header style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ fontSize: '1.5rem', margin: '0 0 0.25rem' }}>Scan-Adoption Dashboard</h1>
        <p style={{ color: '#52525b', margin: '0 0 0.75rem', fontSize: '0.9rem' }}>
          V1.1 30-Tage-Akzeptanz-Gate. Sechs Metriken laut Spec §14.a.
          Nur ADMIN-Zugriff.
        </p>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', fontSize: '0.82rem' }}>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            style={{
              padding: '0.4rem 0.9rem',
              background: '#18181b',
              color: '#ffffff',
              border: 'none',
              borderRadius: '0.35rem',
              cursor: loading ? 'not-allowed' : 'pointer',
              fontSize: '0.82rem',
            }}
          >
            {loading ? 'Lädt…' : 'Aktualisieren'}
          </button>
          {lastLoadedAt ? (
            <span style={{ color: '#71717a' }}>
              Zuletzt geladen: {lastLoadedAt.toLocaleString('de-DE')}
            </span>
          ) : null}
        </div>
      </header>

      {error ? (
        <div
          role="alert"
          style={{
            padding: '0.75rem 1rem',
            background: '#fef2f2',
            border: '1px solid #fecaca',
            color: '#991b1b',
            borderRadius: '0.5rem',
            marginBottom: '1rem',
          }}
        >
          Fehler beim Laden: {error}
        </div>
      ) : null}

      <section
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
          gap: '1rem',
        }}
      >
        {/* (a) Primary adoption ratio */}
        <Tile
          title="(a) Scan-Adoption 30 T"
          subtitle={`Ziel ≥ ${ADOPTION_TARGET}% · Stop-Ship < ${ADOPTION_HALT}%`}
          value={formatPct(metrics?.scan_adoption_pct_30d ?? null)}
          status={adoptionStatus(metrics?.scan_adoption_pct_30d ?? null)}
          footnote="GOLDSMITH · ohne Testnutzer · ohne Korrekturen"
        />

        {/* (a-2) Secondary breadth */}
        <Tile
          title="(a2) Scan-Breite 7 T"
          subtitle="% GOLDSMITHs mit ≥ 1 Scan in 7 T"
          value={formatPct(metrics?.scan_breadth_pct_7d ?? null)}
          status={
            metrics?.scan_breadth_pct_7d == null
              ? 'na'
              : metrics.scan_breadth_pct_7d >= 80
                ? 'ok'
                : metrics.scan_breadth_pct_7d >= 50
                  ? 'yellow'
                  : 'halt'
          }
          footnote="Nutzer-zählend, nicht Zeilen-zählend"
        />

        {/* (b) FAB-tap latency p50 */}
        <Tile
          title="(b) FAB→Timer p50"
          subtitle={`Ziel ≤ ${LATENCY_TARGET_MS / 1000} s`}
          value={formatMs(metrics?.fab_tap_to_timer_ms_p50 ?? null)}
          status={latencyStatus(metrics?.fab_tap_to_timer_ms_p50 ?? null)}
          footnote="client_tap_at → server_resolved_at"
        />

        {/* (b-2) FAB-tap latency p95 */}
        <Tile
          title="(b2) FAB→Timer p95"
          subtitle={`Stop-Ship > ${LATENCY_STOP_SHIP_MS / 1000} s`}
          value={formatMs(metrics?.fab_tap_to_timer_ms_p95 ?? null)}
          status={latencyStatus(metrics?.fab_tap_to_timer_ms_p95 ?? null)}
          footnote="95. Perzentil, 30-Tage-Fenster"
        />

        {/* (c) Alloy-override count */}
        <Tile
          title="(c) Legierungs-Overrides"
          subtitle="30 T · Kategorie erforderlich"
          value={
            metrics ? formatCount(metrics.alloy_override_count_30d) : '—'
          }
          status="ok"
          footnote="Vgl. synthetische QR-Fixtures"
        />

        {/* (d) Camera-denied fallback count */}
        <Tile
          title="(d) Kamera-Fallback"
          subtitle="30 T · Ziel ≥ 1 im Feld"
          value={
            metrics ? formatCount(metrics.camera_fallback_count_30d) : '—'
          }
          status={
            metrics == null
              ? 'na'
              : metrics.camera_fallback_count_30d > 0
                ? 'ok'
                : 'yellow'
          }
          footnote="scan_logs.fallback_reason"
        />

        {/* (e) USB HID count */}
        <Tile
          title="(e) USB HID erkannt"
          subtitle="30 T · Ziel ≥ 1 Werkstatt"
          value={metrics ? formatCount(metrics.usb_hid_scan_count_30d) : '—'}
          status={
            metrics == null
              ? 'na'
              : metrics.usb_hid_scan_count_30d > 0
                ? 'ok'
                : 'yellow'
          }
          footnote="scan_logs.context.input_source"
        />

        {/* (f) Bundle size — not live data. Link to CI trend. */}
        <Tile
          title="(f) Scanner-Bundle"
          subtitle="Ziel ≤ 250 KB gzip (Stop > 400 KB)"
          value="CI"
          status="ok"
          footnote="docs/field-test-kit/bundle-trend.csv"
        />
      </section>

      <footer
        style={{
          marginTop: '2rem',
          fontSize: '0.78rem',
          color: '#71717a',
          borderTop: '1px solid #e4e4e7',
          paddingTop: '1rem',
        }}
      >
        <p style={{ margin: '0 0 0.25rem' }}>
          Quell-Queries: docs/field-test-kit/V1.1-scan-adoption-query.sql
          · V1.1-scan-breadth-query.sql
        </p>
        <p style={{ margin: '0 0 0.25rem' }}>
          UAT-Matrix: docs/field-test-kit/V1.1-uat-acceptance-matrix.md
        </p>
        <p style={{ margin: 0 }}>
          Stilistik absichtlich minimal — UI-Polish ist V1.2-Scope.
        </p>
      </footer>
    </div>
  );
};

export default ScanAdoptionDashboard;
