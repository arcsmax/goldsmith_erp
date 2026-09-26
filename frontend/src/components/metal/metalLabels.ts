// Shared labels and formatters for the metal inventory screens (W4-03).
// One table instead of the three copies the page, the summary cards and the
// usage panel used to keep (with emoji icons, which the playbook forbids).
import type { MetalType } from '../../types';

export interface MetalLabel {
  label: string;
  purity: string;
}

export const METAL_TYPE_LABELS: Readonly<Record<MetalType, MetalLabel>> = {
  gold_24k: { label: 'Gold 24K', purity: '999.9' },
  gold_22k: { label: 'Gold 22K', purity: '916' },
  gold_18k: { label: 'Gold 18K', purity: '750' },
  gold_14k: { label: 'Gold 14K', purity: '585' },
  gold_9k: { label: 'Gold 9K', purity: '375' },
  silver_999: { label: 'Silber 999', purity: '999' },
  silver_925: { label: 'Silber 925', purity: '925' },
  silver_800: { label: 'Silber 800', purity: '800' },
  platinum_950: { label: 'Platin 950', purity: '950' },
  platinum_900: { label: 'Platin 900', purity: '900' },
  palladium: { label: 'Palladium', purity: '999' },
  white_gold_18k: { label: 'Weißgold 18K', purity: '750' },
  white_gold_14k: { label: 'Weißgold 14K', purity: '585' },
  rose_gold_18k: { label: 'Rotgold 18K', purity: '750' },
  rose_gold_14k: { label: 'Rotgold 14K', purity: '585' },
};

export const METAL_TYPES = Object.keys(METAL_TYPE_LABELS) as MetalType[];

/** "Gold 18K"; unknown (custom) codes fall back to the raw value. */
export function metalLabel(metalType: string | null | undefined): string {
  if (!metalType) return '—';
  return METAL_TYPE_LABELS[metalType as MetalType]?.label ?? metalType;
}

/** "Gold 18K (750)" for selects. */
export function metalLabelWithPurity(metalType: MetalType): string {
  const entry = METAL_TYPE_LABELS[metalType];
  return entry ? `${entry.label} (${entry.purity})` : metalType;
}

const GRAMS_PER_KG = 1000;
const WEIGHT_FORMATTER = new Intl.NumberFormat('de-DE', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const PRECISE_WEIGHT_FORMATTER = new Intl.NumberFormat('de-DE', {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
});

/** "12,50 g" or "1,25 kg" from 1000 g. */
export function formatWeight(grams: number): string {
  if (grams >= GRAMS_PER_KG) return `${WEIGHT_FORMATTER.format(grams / GRAMS_PER_KG)} kg`;
  return `${WEIGHT_FORMATTER.format(grams)} g`;
}

/** "0,125 g" for consumption records. */
export function formatPreciseWeight(grams: number): string {
  return `${PRECISE_WEIGHT_FORMATTER.format(grams)} g`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('de-DE');
}

/** A batch counts as used up below this remainder (rounding noise). */
export const DEPLETED_THRESHOLD_G = 0.01;
