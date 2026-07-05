import { useEffect, useRef, useState } from "react";
import type {
  EstimatorMetadata,
  LaborEstimateRequest,
  LaborEstimateResponse,
  Quote,
  QuoteLineItemInput,
} from "../../types";
import { useAuth } from "../../contexts/AuthContext";
import { useToast } from "../../contexts/ToastContext";
import { logError } from "../../lib/logError";
import { estimatesApi } from "../../api/estimates";
import { formatCurrency, formatHours } from "../../utils/formatters";
import {
  SIMILARITY_LEVEL_DESCRIPTION,
  SIMILARITY_LEVEL_LABEL,
} from "./labels";
import styles from "./EstimatorPanel.module.css";

/**
 * Minimal order shape the EstimatorPanel needs.
 *
 * The shared `OrderType` doesn't expose `order_type` or `surface_finish`
 * (those live on the create/update input shapes); the parent QuotesPage
 * already pulls them from the full order detail, so it populates this
 * minimal shape for the panel.
 */
interface EstimatorOrder {
  id: number;
  order_type?: string | null;
  surface_finish?: string | null;
  alloy?: string | null;
}

/**
 * Discriminated union covering every visible state of the panel.
 * - idle       : initial; user can adjust inputs + click "Schätzung holen"
 * - loading    : request in flight
 * - insufficient: backend returned insufficient_data=true (post-decision #1)
 * - result     : a real estimate with P50 + P20/P80 + tier badge
 * - error      : fetch failed; show "Erneut versuchen"
 * - accepting  : onPatch in flight
 * - accepted   : onPatch returned success; show success banner
 */
type PanelState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "insufficient"; response: LaborEstimateResponse }
  | { kind: "result"; response: LaborEstimateResponse; override: string }
  | { kind: "error" }
  | { kind: "accepting" }
  | { kind: "accepted" };

/**
 * What the panel needs from its parent.
 * - quote    : the DRAFT quote to attach the LABOR line to
 * - order    : the linked Order (auto-fills order_type, surface_finish, has_stone_setting)
 * - hasStoneSetting : parent-derived signal; the Order shape in this codebase
 *              doesn't expose a gemstone relation, so the parent must derive this
 *              (e.g. from a separate consultation/material lookup) and pass it in
 * - onPatch  : the parent's save handler for adding a line item. Returns true on
 *              success so the panel can flip to the "accepted" state.
 */
interface EstimatorPanelProps {
  quote: Quote;
  order: EstimatorOrder | null;
  hasStoneSetting?: boolean;
  onPatch: (patch: { addLineItem: QuoteLineItemInput }) => Promise<boolean>;
}

const ESTIMATOR_VERSION = "labor_estimator_v1";

export function EstimatorPanel({
  quote,
  order,
  hasStoneSetting = false,
  onPatch,
}: EstimatorPanelProps) {
  const { hasRole } = useAuth();
  const { showToast } = useToast();
  const [state, setState] = useState<PanelState>({ kind: "idle" });
  const [finishType, setFinishType] = useState<string>("");
  const [complexity, setComplexity] = useState<number>(3);
  const [alloy, setAlloy] = useState<string>("");
  const quoteIdRef = useRef(quote.id);

  // Keep ref pointing at the quote the panel was opened for so we can
  // discard stale responses if the user navigates to a different quote
  // while a request is in flight.
  useEffect(() => {
    quoteIdRef.current = quote.id;
  }, [quote.id]);

  // Role gate: only ADMIN and GOLDSMITH can see/use the estimator.
  // The component returns null rather than rendering a disabled shell —
  // a VIEWER has no business knowing the suggested cost at all.
  if (!hasRole(["ADMIN", "GOLDSMITH"])) return null;

  // Quote state gate: only DRAFT quotes can be edited.
  if (quote.status !== "DRAFT") return null;

  // No order linked → can't build a meaningful estimate request.
  if (!order) {
    return (
      <div className={styles["estimator-panel"]}>
        <div className={styles["estimator-panel__header"]}>
          <h3 className={styles["estimator-panel__title"]}>Kalkulation</h3>
        </div>
        <div className={styles["estimator-panel__disabled"]}>
          Mit einem Auftrag verknüpfen, um die Schätzung zu nutzen.
        </div>
      </div>
    );
  }

  async function handleFetch(): Promise<void> {
    if (state.kind === "loading" || state.kind === "accepting") return;
    if (!order) return; // type narrowing for the closure below
    const request: LaborEstimateRequest = {
      order_type: order.order_type ?? "",
      finish_type: finishType || order.surface_finish || null,
      has_stone_setting: hasStoneSetting,
      alloy: alloy || order.alloy || null,
      complexity_rating: complexity,
    };
    setState({ kind: "loading" });
    try {
      const response = await estimatesApi.getLaborEstimate(request);
      // Stale-response guard: if the user navigated away mid-flight, drop the result.
      if (quoteIdRef.current !== quote.id) return;
      if (response.insufficient_data || response.hours_p50 === null) {
        setState({ kind: "insufficient", response });
      } else {
        setState({
          kind: "result",
          response,
          override: String(response.hours_p50),
        });
      }
    } catch (err: unknown) {
      if (quoteIdRef.current !== quote.id) return;
      logError("estimator.getLaborEstimate", err);
      setState({ kind: "error" });
      showToast("Schätzung konnte nicht geladen werden.", "error");
    }
  }

  async function handleAccept(): Promise<void> {
    if (state.kind !== "result") return;
    const { response, override } = state;
    const quotedHours = parseFloat(override);
    if (!Number.isFinite(quotedHours) || quotedHours < 0) {
      showToast("Ungültige Stundenangabe.", "error");
      return;
    }
    if (response.hours_p50 === null || response.labor_cost_p50 === null) {
      showToast("Keine Schätzung verfügbar.", "error");
      return;
    }
    const unitPrice = response.labor_cost_p50 / response.hours_p50;
    const total = quotedHours * unitPrice;
    const tierLabel = SIMILARITY_LEVEL_LABEL[response.similarity_level];
    const metadata: EstimatorMetadata = {
      suggested_hours: response.hours_p50,
      quoted_hours: quotedHours,
      similarity_level: response.similarity_level,
      sample_size: response.sample_size,
      similar_orders: response.similar_orders,
      estimator_version: ESTIMATOR_VERSION,
    };
    const description = `Arbeitszeit (Schätzung: ${tierLabel}-Tier, ${response.sample_size} Aufträge)`;
    const input: QuoteLineItemInput = {
      line_type: "labor",
      description,
      quantity: quotedHours,
      unit_price: unitPrice,
      estimator_metadata: metadata,
    };
    setState({ kind: "accepting" });
    try {
      const success = await onPatch({ addLineItem: input });
      if (quoteIdRef.current !== quote.id) return;
      if (!success) {
        // Roll back to result so the goldsmith can retry without re-fetching.
        setState({ kind: "result", response, override });
        showToast("Übernahme fehlgeschlagen.", "error");
      } else {
        setState({ kind: "accepted" });
        showToast("Als LABOR-Position übernommen.", "success");
      }
    } catch (err: unknown) {
      if (quoteIdRef.current !== quote.id) return;
      logError("estimator.handleAccept", err);
      setState({ kind: "result", response, override });
      showToast("Übernahme fehlgeschlagen.", "error");
    }
  }

  // Helper to convert hours (estimator units) → minutes (formatters.ts).
  const toMinutes = (hours: number): number => hours * 60;

  return (
    <div className={styles["estimator-panel"]}>
      <div className={styles["estimator-panel__header"]}>
        <h3 className={styles["estimator-panel__title"]}>Kalkulation</h3>
      </div>

      {state.kind === "idle" && (
        <>
          <p className={styles["estimator-panel__helper"]}>
            Basiert auf abgeschlossenen Aufträgen. Optional: Finish, Legierung
            und Komplexität anpassen.
          </p>
          <div className={styles["estimator-panel__override"]}>
            <label htmlFor="estimator-finish">Finish</label>
            <select
              id="estimator-finish"
              value={finishType}
              onChange={(e) => setFinishType(e.target.value)}
            >
              <option value="">Keine Angabe</option>
              <option value="Hochglanzpolitur">Hochglanzpolitur</option>
              <option value="Mattiert">Mattiert</option>
              <option value="Gebürstet">Gebürstet</option>
            </select>
          </div>
          <div className={styles["estimator-panel__override"]}>
            <label htmlFor="estimator-alloy">Legierung</label>
            <input
              id="estimator-alloy"
              type="text"
              value={alloy}
              onChange={(e) => setAlloy(e.target.value)}
              placeholder="z.B. gold_750"
            />
          </div>
          <div className={styles["estimator-panel__override"]}>
            <label htmlFor="estimator-complexity">Komplexität (1–5)</label>
            <input
              id="estimator-complexity"
              type="number"
              min={1}
              max={5}
              value={complexity}
              onChange={(e) => {
                const parsed = parseInt(e.target.value, 10);
                setComplexity(Number.isFinite(parsed) ? parsed : 3);
              }}
            />
          </div>
          <button
            type="button"
            className={styles["estimator-panel__accept"]}
            onClick={handleFetch}
            data-testid="estimator-fetch-button"
          >
            Schätzung holen
          </button>
        </>
      )}

      {state.kind === "loading" && (
        <p>
          <span
            className={styles["estimator-panel__spinner"]}
            data-testid="estimator-loading-spinner"
          />{" "}
          Berechne Schätzung…
        </p>
      )}

      {state.kind === "insufficient" && (
        <div
          className={styles["estimator-panel__insufficient"]}
          data-testid="estimator-insufficient"
        >
          Zu wenige ähnliche Aufträge — bitte Stunden manuell eingeben.
        </div>
      )}

      {state.kind === "result" && state.response.hours_p50 !== null && state.response.labor_cost_p50 !== null && (
        <div className={styles["estimator-panel__result"]}>
          <div
            className={styles["estimator-panel__big-number"]}
            data-testid="estimator-cost"
          >
            {formatCurrency(state.response.labor_cost_p50)}
          </div>
          <div
            className={styles["estimator-panel__hours"]}
            data-testid="estimator-hours"
          >
            ≈ {formatHours(toMinutes(state.response.hours_p50))} Stunden
          </div>
          <span
            className={styles["estimator-panel__badge"]}
            data-testid="estimator-tier"
          >
            {SIMILARITY_LEVEL_LABEL[state.response.similarity_level]}
          </span>
          <details className={styles["estimator-panel__details"]}>
            <summary>Details (intern)</summary>
            <p>
              <strong>Bereich:</strong>{" "}
              {state.response.hours_p20 !== null && state.response.hours_p80 !== null
                ? `${formatHours(toMinutes(state.response.hours_p20))}–${formatHours(
                    toMinutes(state.response.hours_p80),
                  )} Stunden`
                : "n/v"}
            </p>
            <p>
              <strong>Stichprobe:</strong> {state.response.sample_size} ähnliche
              Aufträge
            </p>
            <p>
              <strong>Ähnlichkeit:</strong>{" "}
              {SIMILARITY_LEVEL_DESCRIPTION[state.response.similarity_level]}
            </p>
            <p>
              <strong>Ähnliche Aufträge:</strong>
            </p>
            <ul>
              {state.response.similar_orders.slice(0, 10).map((id) => (
                <li key={id}>#{id}</li>
              ))}
            </ul>
          </details>
          <div className={styles["estimator-panel__override"]}>
            <label htmlFor="estimator-override">Stunden manuell anpassen</label>
            <input
              id="estimator-override"
              type="number"
              min={0}
              step={0.25}
              value={state.override}
              onChange={(e) =>
                setState({ ...state, override: e.target.value })
              }
              data-testid="estimator-override-input"
            />
          </div>
          <button
            type="button"
            className={styles["estimator-panel__accept"]}
            onClick={handleAccept}
            data-testid="estimator-accept-button"
          >
            {parseFloat(state.override) === state.response.hours_p50
              ? "Übernehmen"
              : `Mit ${state.override} Stunden übernehmen`}
          </button>
        </div>
      )}

      {state.kind === "accepting" && <p>Übernehme…</p>}

      {state.kind === "accepted" && (
        <div
          className={styles["estimator-panel__success"]}
          data-testid="estimator-accepted"
        >
          ✓ Übernommen als LABOR-Position
        </div>
      )}

      {state.kind === "error" && (
        <button
          type="button"
          className={styles["estimator-panel__accept"]}
          onClick={handleFetch}
          data-testid="estimator-retry-button"
        >
          Erneut versuchen
        </button>
      )}
    </div>
  );
}