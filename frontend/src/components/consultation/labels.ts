// labels.ts — shared German label maps for the Beratungs-Wizard.
//
// Extracted from OccasionBudgetStep/WishStep/PhotoStep/StyleNoGoStep (each
// still re-exports its own map for backwards compatibility) so consumers
// that only need a label lookup — ConsultationsPage (list cards) and
// SummaryStep (customer-presentable read-back) — don't have to pull in the
// full step component (and everything IT imports) just for a Record<K, V>.
import {
  ConsultationOccasion,
  ConsultationPieceType,
  ConsultationPhotoKind,
  NoGoCategory,
} from '../../types';

export const OCCASION_LABELS: Record<ConsultationOccasion, string> = {
  engagement: 'Verlobung',
  wedding: 'Hochzeit',
  anniversary: 'Jahrestag',
  birthday: 'Geburtstag',
  self: 'Für mich selbst',
  redesign: 'Umarbeitung',
  repair_consult: 'Reparatur-Beratung',
  other: 'Anderer Anlass',
};

export const PIECE_TYPE_LABELS: Record<ConsultationPieceType, string> = {
  ring: 'Ring',
  chain: 'Kette',
  pendant: 'Anhänger',
  earrings: 'Ohrringe',
  bracelet: 'Armband',
  brooch: 'Brosche',
  repair: 'Reparatur',
  custom: 'Sonderanfertigung',
};

export const PHOTO_KIND_LABELS: Record<ConsultationPhotoKind, string> = {
  sketch: 'Skizze',
  reference: 'Referenz',
  inspiration: 'Inspiration',
  existing_piece: 'Mitgebrachtes Stück',
};

export const NO_GO_CATEGORY_LABELS: Record<NoGoCategory, string> = {
  metal: 'Metall',
  stone: 'Stein',
  finish: 'Oberfläche',
  design_element: 'Designelement',
  allergy: 'Allergie',
  other: 'Sonstiges',
};
