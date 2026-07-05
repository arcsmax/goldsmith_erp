import type { SimilarityLevel } from "../../types";

// German labels for the 5 similarity tiers the estimator can return.
// Used by EstimatorPanel to badge each estimate and to build the line
// item description when the goldsmith accepts the suggestion.
export const SIMILARITY_LEVEL_LABEL: Record<SimilarityLevel, string> = {
  exact: "Exakt",
  type_finish: "Typ + Finish",
  type: "Typ",
  workshop: "Werkstatt-weit",
  insufficient: "Zu wenig Daten",
};

// Long-form description of what each tier actually means in terms of
// the comparable orders considered. Shown in the collapsible details
// panel so the goldsmith can sanity-check the trust badge.
export const SIMILARITY_LEVEL_DESCRIPTION: Record<SimilarityLevel, string> = {
  exact: "Aufträge mit gleichem Typ, Finish und Steinfassung",
  type_finish: "Aufträge mit gleichem Typ und Finish",
  type: "Aufträge mit gleichem Typ",
  workshop: "Alle abgeschlossenen Werkstattaufträge",
  insufficient: "Zu wenige vergleichbare Aufträge",
};